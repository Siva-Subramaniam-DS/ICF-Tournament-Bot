#!/bin/bash
# ICF Tournament Bot Railway deployment script
# Last Updated: September 7, 2025
echo "Starting ICF Tournament Bot deployment..."
pip install --upgrade pip
pip uninstall -y emoji pilmoji
pip install emoji==1.6.3
pip install pilmoji==2.0.0
pip install -r requirements.txt
echo "Deployment complete!"