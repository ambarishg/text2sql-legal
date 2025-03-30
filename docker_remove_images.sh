sudo chmod 666 /var/run/docker.sock
# Remove all images (force removal)
docker rmi $(docker images -q) -f
