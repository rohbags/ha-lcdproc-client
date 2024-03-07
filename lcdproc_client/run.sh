#!/usr/bin/with-contenv bashio

echo "Starting the Home Assistant LCDproc client!"

#echo -e "TOKEN:"
#echo $SUPERVISOR_TOKEN

#python3 lcdproc_c.py
echo "launching lcdproc_c..."
python3 /lcdproc_c.py



