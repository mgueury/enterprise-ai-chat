FROM oraclelinux:8

RUN dnf module enable -y nodejs:20 && \
    dnf install -y nodejs python3 && \    
     rm -rf /var/cache/dnf

WORKDIR /app
COPY ./ /app/
RUN npm install
CMD exec node rest.js