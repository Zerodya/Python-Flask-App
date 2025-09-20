# Python Flask web app con Docker, Apparmor e Seccomp 
La nostra applicazione python si trova in [app.py](./app.py), che poi lanciamo dentro un container Docker grazie al nostro [Dockerfile](./Dockerfile)

## Passaggi 

### Istalla
- Docker 
- Apparmor
  - metti `apparmor-flask` in `/etc/apparmor.d/`

**Dipendenze per il docker e lo script `seccomp-minimizer.py`:**

`poetry python313Packages.flask apparmor-parser strace websocat python313Packages.requests`

### 1. Build del container docker
`docker build . -t flask:0.0.3`

### 2. Genera un file seccomp che abbia solo le systemcall utilizzate dalla nostra applicazione
`python3 ./seccomp-minimizer.py`

### 3. Avvia il container docker
```
docker run -it --rm \
        --security-opt seccomp=./seccomp.json \
        --security-opt apparmor=apparmor-flask \
        -p 5000:5000 flask:0.0.3
```

## Informazioni utili
- Nel file apparmor abbiamo `/app/data.txt rw` perche' `app.py` deve poter scrivere in `data.txt`