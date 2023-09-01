


# Standard ports:
Sinus : 1233
Sensoren : 1234 - 1237
Cross traffic : 4040

Sensor-view at pi2 scans only ports 1200 - 1250 for traffic


#  query-sensors
"Could not connect" -> `systemctl restart brickd`

# are all vlan interfaces up?

# Switch
Ports 2-8 must be in trunk mode

# Cross traffic

# arp
static arp configuration (via /etc/ethers) on pi1, so it can send traffic for pi2 to the switch even if the switch is blocked by high priority cross traffic
might have to be set manually! > ```sudo arp -s ....```
