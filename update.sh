#!/bin/bash
git pull
sudo systemctl daemon-reload
sudo systemctl restart pyconjp-ticket.service