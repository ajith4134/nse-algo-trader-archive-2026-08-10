# Run the dashboard permanently (survives reboots)

One-time setup (run on the VPS):

    sudo cp /home/opc/nse-algo-trader/deploy/nse-dashboard.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now nse-dashboard

Check it:  sudo systemctl status nse-dashboard
Logs:      journalctl -u nse-dashboard -f
Restart:   sudo systemctl restart nse-dashboard

The dashboard then always runs on port 8080 and restarts on crash/reboot.
Access token is in ~/.nse_algo_trader/dashboard_access_token.txt.
