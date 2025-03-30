sudo chmod 666 /var/run/docker.sock

az acr create --resource-group rgmisron --name misronacr --sku Basic

az acr login -n misronacr

docker tag legalresearcher:latest misronacr.azurecr.io/legalresearcher:v4

docker push misronacr.azurecr.io/legalresearcher:v4