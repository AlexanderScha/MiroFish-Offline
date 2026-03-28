# LAN Access Configuration

## ✅ Configuration Complete

MiroFish-Offline is now configured for LAN access from your office machine.

### 🌐 Access URLs

**From your office machine, use:**
- **Frontend**: http://192.168.1.153:3000
- **Backend API**: http://192.168.1.153:5001
- **Neo4j Browser**: http://192.168.1.153:7474

### 🔥 Firewall Configuration

If you can't reach the services from your office machine, you may need to open the firewall ports:

**Check firewall status:**
```bash
sudo ufw status
```

**Open required ports (if firewall is active):**
```bash
# Allow access from your entire LAN subnet
sudo ufw allow from 192.168.1.0/24 to any port 3000 comment 'MiroFish Frontend'
sudo ufw allow from 192.168.1.0/24 to any port 5001 comment 'MiroFish Backend'
sudo ufw allow from 192.168.1.0/24 to any port 7474 comment 'Neo4j Browser'
sudo ufw allow from 192.168.1.0/24 to any port 7687 comment 'Neo4j Bolt'

# Or, more restrictively, allow from specific office machine IP only:
# sudo ufw allow from YOUR_OFFICE_IP to any port 3000
# sudo ufw allow from YOUR_OFFICE_IP to any port 5001
# sudo ufw allow from YOUR_OFFICE_IP to any port 7474
# sudo ufw allow from YOUR_OFFICE_IP to any port 7687
```

**Alternative: Use iptables (if not using UFW):**
```bash
# Check current rules
sudo iptables -L -n

# If DROP policy is blocking, add rules:
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 3000 -j ACCEPT
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 5001 -j ACCEPT
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 7474 -j ACCEPT
sudo iptables -A INPUT -p tcp -s 192.168.1.0/24 --dport 7687 -j ACCEPT
```

### 🔒 Security Considerations

**Current security status:**
- ✅ Configured for private LAN access only
- ⚠️ NO authentication enabled
- ⚠️ NO encryption (HTTP, not HTTPS)
- ⚠️ CORS allows all origins

**This is SAFE if:**
- ✅ You trust everyone on your LAN (192.168.1.x)
- ✅ Your router/firewall blocks external access
- ✅ You're on a private home/office network
- ✅ No port forwarding to the internet

**This is UNSAFE if:**
- ❌ Ports are exposed to the internet
- ❌ You're on a shared/public network
- ❌ Untrusted devices can access your LAN

### 🛡️ Recommended Security Improvements for LAN

If you want to keep it running on LAN but more securely:

1. **Restrict to specific IP:**
   Edit `.env` and update firewall to only allow your office machine's specific IP

2. **Use SSH tunnel instead:**
   ```bash
   # From your office machine:
   ssh -L 3000:localhost:3000 -L 5001:localhost:5001 tank@192.168.1.153
   # Then access via http://localhost:3000 on office machine
   ```

3. **Set up reverse proxy with auth:**
   - Install nginx
   - Configure basic auth
   - Add SSL certificate

### 📍 Network Information

- **Server IP**: 192.168.1.153
- **Network**: 192.168.1.0/24
- **Services bound to**: 0.0.0.0 (all interfaces)

### 🧪 Testing from Office Machine

**Test connectivity:**
```bash
# From your office machine:
ping 192.168.1.153

# Test if ports are reachable:
nc -zv 192.168.1.153 3000
nc -zv 192.168.1.153 5001
nc -zv 192.168.1.153 7474

# Or use curl:
curl http://192.168.1.153:5001/health
```

**If you get connection refused:**
1. Check firewall (see above)
2. Verify services are running: `./start-local.sh`
3. Check logs: `tail -f logs/backend.log`

### 🔄 Changing Back to Localhost Only

If you want to restrict back to localhost-only access:

1. Edit `frontend/vite.config.js`:
   ```javascript
   host: 'localhost',  // Change from '0.0.0.0'
   ```

2. Edit `.env`:
   ```bash
   FLASK_HOST=127.0.0.1  # Change from 0.0.0.0
   ```

3. Restart: `./stop-local.sh && ./start-local.sh`

### ⚡ Quick Commands

**Restart services:**
```bash
./stop-local.sh && ./start-local.sh
```

**View logs:**
```bash
tail -f logs/backend.log logs/frontend.log
```

**Check what's listening:**
```bash
ss -tlnp | grep -E ":3000|:5001|:7474"
```

---

**Remember**: This setup is for **PRIVATE LAN ONLY**. Never expose these ports to the internet without proper authentication and encryption!
