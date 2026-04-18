FROM python:3.11-alpine

WORKDIR /app

COPY netstat_server.py .

ENV NETWORK_INTERFACE=${NETWORK_INTERFACE}
ENV NETSTAT_PORT=8085

EXPOSE 8085

CMD ["python", "netstat_server.py"]
