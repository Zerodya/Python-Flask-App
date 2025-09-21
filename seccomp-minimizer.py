#!/usr/bin/env python3
"""
Script per minimizzare seccomp.json per un container con applicazione Flask.

Questo script rimuove sistematicamente le system call dal profilo seccomp
assicurandosi che il container possa comunque:
1. Avviarsi senza errori
2. Rispondere entro un timeout
3. Servire richieste HTTP
4. Gestire invii di form e scrittura di file
"""

import json
import subprocess
import time
import requests
import sys
import os
from typing import List, Dict, Any

# Flag verboso per output dettagliato
VERBOSE = True

def log(message: str):
    """Stampa messaggi informativi se il verbose è attivo."""
    if VERBOSE:
        print(f"[INFO] {message}")

def stop_all_containers():
    """Ferma e rimuove tutti i container Docker in esecuzione."""
    log("Arresto di tutti i container Docker in esecuzione...")
    try:
        # Ottieni lista dei container in esecuzione
        result = subprocess.run(
            ["docker", "ps", "-q"], 
            capture_output=True, 
            text=True
        )
        
        if result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            log(f"Trovati {len(container_ids)} container in esecuzione")
            
            # Ferma tutti i container
            subprocess.run(
                ["docker", "stop"] + container_ids,
                check=True,
                capture_output=True
            )
            log("Tutti i container fermati con successo")
            
            # Rimuovi tutti i container
            subprocess.run(
                ["docker", "rm"] + container_ids,
                check=True,
                capture_output=True
            )
            log("Tutti i container rimossi con successo")
        else:
            log("Nessun container in esecuzione trovato")
    except subprocess.CalledProcessError as e:
        log(f"Attenzione: impossibile fermare/rimuovere i container: {e}")

def load_seccomp_profile(filepath: str) -> Dict[str, Any]:
    """Carica il profilo seccomp da un file JSON."""
    log(f"Caricamento del profilo seccomp da {filepath}")
    with open(filepath, 'r') as f:
        return json.load(f)

def save_seccomp_profile(profile: Dict[str, Any], filepath: str):
    """Salva il profilo seccomp in un file JSON."""
    log(f"Salvataggio del profilo seccomp in {filepath}")
    with open(filepath, 'w') as f:
        json.dump(profile, f, indent=2)

def get_all_syscalls(profile: Dict[str, Any]) -> List[str]:
    """Estrae tutti i nomi delle system call dal profilo seccomp."""
    syscalls = []
    for syscall_group in profile.get('syscalls', []):
        syscalls.extend(syscall_group.get('names', []))
    return sorted(list(set(syscalls)))

def remove_syscall_from_profile(profile: Dict[str, Any], syscall_name: str) -> Dict[str, Any]:
    """Crea un nuovo profilo rimuovendo la system call specificata."""
    new_profile = json.loads(json.dumps(profile))  # Deep copy
    
    # Rimuove la syscall da tutti i gruppi
    for syscall_group in new_profile.get('syscalls', []):
        if 'names' in syscall_group and syscall_name in syscall_group['names']:
            syscall_group['names'].remove(syscall_name)
    
    return new_profile

def run_container_with_profile(profile_path: str, timeout: int = 30) -> bool:
    """
    Esegue il container con il profilo seccomp specificato.
    Ritorna True se ha successo, False altrimenti.
    """
    log(f"Test del container con profilo: {profile_path}")
    
    try:
        # Avvia container in background
        cmd = [
            "docker", "run", "-d", "--rm",
            f"--security-opt=seccomp={profile_path}",
            "--security-opt=apparmor=apparmor-flask",
            "-p", "5000:5000",
            "flask:0.0.3"
        ]
        
        log(f"Esecuzione comando: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            log(f"Avvio del container fallito: {result.stderr}")
            return False
            
        container_id = result.stdout.strip()
        log(f"Container avviato con ID: {container_id}")
        
        # Attendi un po’ per l’inizializzazione
        time.sleep(5)
        
        # Verifica se il container è ancora in esecuzione
        inspect_result = subprocess.run(
            ["docker", "inspect", container_id],
            capture_output=True,
            text=True
        )
        
        if inspect_result.returncode != 0:
            log("Impossibile ispezionare il container")
            return False
            
        container_info = json.loads(inspect_result.stdout)
        if not container_info[0]['State']['Running']:
            log("Il container non è in esecuzione")
            # Mostra i log per capire cosa è andato storto
            logs_result = subprocess.run(
                ["docker", "logs", container_id],
                capture_output=True,
                text=True
            )
            if logs_result.returncode == 0:
                log(f"Log del container: {logs_result.stdout}")
            return False
            
        log("Il container è in esecuzione")
        return True
        
    except subprocess.TimeoutExpired:
        log("Timeout durante l’avvio del container")
        return False
    except Exception as e:
        log(f"Errore nell’esecuzione del container: {e}")
        return False

def test_web_functionality() -> bool:
    """
    Verifica se l’applicazione web funziona correttamente.
    Ritorna True se tutti i test passano, False altrimenti.
    """
    log("Test della funzionalità web...")
    
    try:
        # Test 1: Caricamento pagina principale
        log("Test accesso alla pagina principale...")
        response = requests.get("http://localhost:5000/", timeout=10)
        if response.status_code != 200:
            log(f"Pagina principale fallita con status {response.status_code}")
            return False
        log("Pagina principale caricata con successo")
        
        # Test 2: Invio form
        log("Test invio form...")
        response = requests.post(
            "http://localhost:5000/write",
            data={"content": "test_content"},
            timeout=10
        )
        if response.status_code != 200:
            log(f"Invio form fallito con status {response.status_code}")
            return False
        log("Invio form riuscito")
        
        return True
        
    except requests.exceptions.RequestException as e:
        log(f"Test funzionalità web fallito: {e}")
        return False
    except Exception as e:
        log(f"Errore inaspettato durante test web: {e}")
        return False

def stop_container():
    """Ferma il container di test."""
    try:
        # Trova e ferma il container
        result = subprocess.run(
            ["docker", "ps", "-q", "--filter", "ancestor=flask:0.0.3"],
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            for container_id in container_ids:
                subprocess.run(
                    ["docker", "stop", container_id],
                    capture_output=True
                )
                log(f"Fermato container {container_id}")
    except Exception as e:
        log(f"Errore fermando il container: {e}")

def minimize_seccomp_profile():
    """Funzione principale per minimizzare il profilo seccomp."""
    log("Inizio minimizzazione del profilo seccomp...")
    
    # Ferma tutti i container
    stop_all_containers()
    
    # Carica profilo di default (permissivo)
    default_profile = load_seccomp_profile("seccomp-default.json")
    
    # Crea profilo iniziale di lavoro (copia del default)
    working_profile = json.loads(json.dumps(default_profile))
    working_profile_path = "seccomp.json"
    save_seccomp_profile(working_profile, working_profile_path)
    
    # Ottieni tutte le syscalls
    all_syscalls = get_all_syscalls(working_profile)
    log(f"Trovate {len(all_syscalls)} system call da testare")
    
    # Lista delle syscalls necessarie
    necessary_syscalls = set()
    
    # Testa ogni syscall
    for i, syscall in enumerate(all_syscalls):
        log(f"Test syscall {i+1}/{len(all_syscalls)}: {syscall}")
        
        # Crea profilo senza questa syscall
        test_profile = remove_syscall_from_profile(working_profile, syscall)
        test_profile_path = f"seccomp_test_{syscall}.json"
        save_seccomp_profile(test_profile, test_profile_path)
        
        try:
            # Ferma eventuale container
            stop_container()
            
            # Testa il profilo
            if run_container_with_profile(test_profile_path):
                # Se il container parte, verifica la funzionalità web
                if test_web_functionality():
                    log(f"La syscall {syscall} NON è necessaria - può essere rimossa")
                    # Aggiorna profilo di lavoro
                    working_profile = test_profile
                    save_seccomp_profile(working_profile, working_profile_path)
                else:
                    log(f"La syscall {syscall} è necessaria per la funzionalità web")
                    necessary_syscalls.add(syscall)
            else:
                log(f"La syscall {syscall} è necessaria per l’avvio del container")
                necessary_syscalls.add(syscall)
                
        except Exception as e:
            log(f"Errore durante test della syscall {syscall}: {e}")
            necessary_syscalls.add(syscall)
        finally:
            # Ferma container e rimuovi file di test
            stop_container()
            try:
                os.remove(test_profile_path)
            except:
                pass
    
    # Pulizia finale
    stop_container()
    
    # Salva profilo minimizzato
    save_seccomp_profile(working_profile, "seccomp-minimized.json")
    
    # Report risultati
    log("=== MINIMIZZAZIONE COMPLETATA ===")
    log(f"Syscall necessarie ({len(necessary_syscalls)}):")
    for syscall in sorted(necessary_syscalls):
        log(f"  - {syscall}")
    
    log("Profilo minimizzato salvato come seccomp-minimized.json")
    log("Ora puoi usare questo profilo con il tuo container")

if __name__ == "__main__":
    try:
        minimize_seccomp_profile()
    except KeyboardInterrupt:
        log("Minimizzazione interrotta dall’utente")
        stop_container()
        sys.exit(1)
    except Exception as e:
        log(f"Minimizzazione fallita con errore: {e}")
        stop_container()
        sys.exit(1)
