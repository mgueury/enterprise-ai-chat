FROM oraclelinux:8

RUN dnf module enable -y nodejs:20 && \
    dnf install -y nodejs python3 && \    
     dnf install -y oracle-instantclient-release-el8 && \
     dnf install -y oracle-instantclient-basic oracle-instantclient-sqlplus && \    
     rm -rf /var/cache/dnf

WORKDIR /app
COPY ./ /app/
RUN npm install
CMD exec node rest.js