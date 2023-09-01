# Setting up a vlan interface

Create new subinterface
```bash
sudo ip link add link eth0 name eth0.0 type vlan id 16 egress-qos-map 0:0 1:1 2:2 3:3 4:4 5:5 6:6 7:7
```

Give interace an ip address
```bash
sudo ip addr add 10.16.0.10/24 dev eth0.0
```


Set status to up
```bash
sudo ip link set eth0.0 up
```

If the sink is not in the same vlan, manually set an arp entry
```bash
sudo arp -s 10.16.1.2 00:19:99:aa:bb:cc -i eth0.0
```


# Wilde portweiterleitungen

ssh port weiterleiten
```bash
ssh -L 9988:172.16.38.101:22001 -N 172.16.45.10
```

und nach außen weiterleiten, dass die existierende ssh verbindung verwendet werden kann
```bash
ssh -L 9999:localhost:1234 -N -p 9988 demo@localhost
```
