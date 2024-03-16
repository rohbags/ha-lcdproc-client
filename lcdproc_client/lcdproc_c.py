
## copyright 2024 Rohan Murch rohan.murch@gmail.com
## you're welcome :)

import socket
import json
import re
import time
import os
import threading
import requests
import atexit
import datetime


print ("Loaded lcdproc_c.py...")

json_file = 'options.json'
with open(json_file) as json_data:
    jdata = json.load(json_data)
print ("lcdproc_host:  [", jdata['lcdproc_host'], "]")
print ("lcdproc_port:  [", jdata['lcdproc_port'], "]")
print ("show_default:  [", jdata['show_default'], "]")
print ("show_cpu:      [", jdata['show_cpu'], "]")
print ("show_mem:      [", jdata['show_mem'], "]")
print ("show_net:      [", jdata['show_net'], "]")
print ("show_disk:     [", jdata['show_disk'], "]")
print ("show_sensors:  [", jdata['show_sensors'], "]")
print ("debug:         [", jdata['debug'], "]")

# sanity check
if jdata['lcdproc_host'] == "":
  print ("ERROR: no lcdproc server host set!")
  exit(1)


## is debug mode?
debug = False
if jdata['debug'] == True:
  debug = True

## API token
token = os.environ["SUPERVISOR_TOKEN"]
if debug: print("API Token: ", token)

api_headers = {'Authorization':'Bearer ' + token, 'Content-Type':'application/json'}

## for testing new sensors etc
##api_res = requests.get('http://supervisor/core/api/states/sensor.house_meter_power', headers=api_headers) # ?
#if debug: 
#  api_res = requests.get('http://supervisor/core/api/states/binary_sensor.garage_door_status', headers=api_headers) # ?
#  print("test1d api request:")
#  print( api_res )
#  print("json1d:")
#  print( api_res.json() )

api_res = requests.get('http://supervisor/supervisor/info', headers=api_headers) # ?
sys_tz = api_res.json()['data']['timezone']
if debug: print ("sys_tz: ", sys_tz )
sys_var = dict(tz = api_res.json()['data']['timezone'], debug = api_res.json()['data']['debug'])
print ("sys_var tz: ", sys_var['tz'] )
if debug: print ("sys_var debug: ", sys_var['debug'] )


## globals
do_screen = False;
do_widget = "";
sensors = []


def receive(socket, signal):
    global do_screen
    global do_widget
    while signal:
        try:
            data = socket.recv(1024)
        except:
            print("You have been disconnected from the server?")
            signal = False
            do_screen = False
            break
        else:
          darr = str(data.decode("utf-8")).splitlines(True)
          for data in darr:
            if data == "success\n":
#              print("IS_SUCCESS")
              continue
            m = re.compile("^huh\?\s(.+)\n$").match(data)
            if m:
              print("Server reported error: ", m.group(1))
              continue
            pattern = re.compile("^menuevent\s(\w+)\s(\w+)\s(\w+)?\n$")
            m = pattern.match(data)
            if m:
              print("Menuevent:"+ m.group(1) +" type:"+ m.group(2) +" id:"+ m.group(3) + " [value:"+ m.group(4) +"]")
              continue
            pattern = re.compile("^(\w+)\s(\w+)\n$")
            m = pattern.match(data)
            if m:
              if m.group(1) == "listen":
                do_widget = m.group(2)
                do_screen = True;
              elif m.group(1) == "ignore":
                do_screen = False;
                do_widget = ""
              elif m.group(1) == "key":
                print("server cmd->key: ", m.group(2))
            else:
              print("ERROR: cant decode cmd: ["+ data +"]" )


sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
receiveThread = threading.Thread(target = receive, args = (sock, True))

## send data function
def send_data(msg):
  sent = sock.send(str.encode(msg+"\n"))
  if sent == 0:
    raise RuntimeError("socket connection broken")
  if receiveThread.is_alive() == False:
    if debug: print("send_data: " + msg)
    response = sock.recv(4096)
    if debug: print ("LCDproc said: ", response.decode("utf-8").rstrip())
  

## get Supervisor API data
def get_api(type):
  global api_headers
  if type == "default":
    api_res = requests.get('http://supervisor/host/info', headers=api_headers)
    if api_res.status_code != 200:
      print("API Error")
    ret = api_res.json()
    return ret['data']['operating_system'], ret['data']['kernel'], ret['data']['boot_timestamp']
  elif type == "cpu":
#    api_res = requests.get('http://supervisor/core/stats', headers=api_headers)
    api_res = requests.get('http://supervisor/core/api/states/sensor.processor_use', headers=api_headers)
    if api_res.status_code != 200:
      print("API Error")
    ret = api_res.json()
#    return ret['data']['cpu_percent']
    api_res = requests.get('http://supervisor/core/api/states/sensor.processor_temperature', headers=api_headers)
    if api_res.status_code != 200:
      print("API Error")
    ret2 = api_res.json()

    return ret['state'], ret2['state']

    
  elif type == "mem":
    api_res = requests.get('http://supervisor/core/stats', headers=api_headers)
    if api_res.status_code != 200:
      print("API Error")
    ret = api_res.json()
    return ret['data']['memory_percent'], ret['data']['memory_usage'], ret['data']['memory_limit']
  elif "ha_sensor" in type:
    sensor_id = ""
    for s in sensors:
      if s[0] == type:
        sensor_id = s[1]
        break
    if sensor_id == "":
      print("ERROR: no sensor_id found for ", type)
      return "null","null","null"
#    api_res = requests.get('http://supervisor/core/api/states/sensor.house_meter_power', headers=api_headers)
    api_res = requests.get('http://supervisor/core/api/states/'+str(sensor_id), headers=api_headers)
    if api_res.status_code != 200:
      print("API Error")
    ret = api_res.json()
    ## handle different sensors here - more to do
    s_type = sensor_id.split('.')
    value = ""
    if s_type[0] == "sensor":
      if ret['attributes']['device_class'] == "temperature":  ##  °C becomes A°C on lcd display????
        value = ret['state'] + "°C"
      else:
        value = ret['state'] +" "+ ret['attributes']['unit_of_measurement']
    elif s_type[0] == "binary_sensor":
      if ret['attributes']['device_class'] == "garage_door" or "door" or "window" or "opening":
        if ret['state'] == "on":
          value = "Open"
        else:
          value = "Closed"
    else:
#      print("ERROR: unknown sensor type:", s_type[0] )
      value = ret['state'] +" "+ ret['attributes']['unit_of_measurement']
    return value, ret['attributes']['friendly_name'], ret['last_updated']
  elif type == "disk":
    api_res = requests.get('http://supervisor/host/info', headers=api_headers)
    if api_res.status_code != 200:
      print("API Error")
    ret = api_res.json()
    return ret['data']['disk_free'], ret['data']['disk_used'], ret['data']['disk_total']
  else:
    print("Error: unknown get_api type: ", type)
    

## turn bytes to kb/mb/gb/etc
def bytesto(bytes, to, bsize=1024): 
    a = {'k' : 1, 'm': 2, 'g' : 3, 't' : 4, 'p' : 5, 'e' : 6 }
    r = float(bytes)
    return round(bytes / (bsize ** a[to]))


## cal uptime from epoch boot timestamp in microseconds to days, hours, mins, secs
def calc_uptime(unix):
  unix = unix / 1e6
  dt1 = datetime.datetime.fromtimestamp(unix, datetime.timezone.utc)
  now = datetime.datetime.now(datetime.timezone.utc)
  diff = now - dt1
  days, seconds = diff.days, diff.seconds
  hours = seconds // 3600
  minutes = (seconds % 3600) // 60
  seconds = (seconds % 60)
  return str(days)+" Days "+str(hours)+":"+str(minutes)+":"+str(seconds)


## pad text to centre of screen
## TODO: remove 'size' option, get from sys_var
def centre_text(text, size):
  tsize = len(text)
  size = int(sys_var['wid'])
  tfree = size - tsize
  if ((tfree/2) % 2) == 0: # is even
    rbuf = int(tfree/2)
    lbuf = int(tfree/2)
  else: # is odd
    tfree = tfree - 1
    rbuf = int(tfree/2)
    lbuf = int((tfree/2) + 1)
  ret = ""
  for _ in range(lbuf):
    ret += " "
  ret += text
  for _ in range(rbuf):
    ret += " "
#  if debug: print("centre_text: [" + ret +"]")
  return str(ret)


## last updated (for sensors)
## eg: 'last_updated': '2024-03-06T02:00:55.017979+00:00'
def last_update(lu):
  then = datetime.datetime.strptime(lu, "%Y-%m-%dT%H:%M:%S.%f%z")
  now = datetime.datetime.now(datetime.timezone.utc)
  duration = now - then
  if duration.total_seconds() < 10: # 9.9 secs
    ret = str(float('%.1f' % duration.total_seconds())) + " secs"
  elif duration.total_seconds() < 99: # 99 secs
    ret = str(round(duration.total_seconds())) + " secs"
  elif duration.total_seconds() >= 99 and duration.total_seconds() < 5400: # 90 mins
    ret = str(round( (duration.total_seconds()%3600)//60 )) + " mins"
  elif duration.total_seconds() >= 5400 and duration.total_seconds() < 86400: # 24 hours
    ret = str(round(duration.total_seconds()//3600)) + " hours"
  elif duration.total_seconds() >= 86400: # greater than 24h, days
    ret = str(round(duration.total_seconds()//86400)) + " days"
  else:
    ret = str(round(duration.total_seconds()) ) + " ?"
  return ret


# screen run thread
def run_screen():
    global do_screen
    global do_widget
    while True:
            if do_screen == True:
              if do_widget == "ha_client":
                while do_screen == True and do_widget == "ha_client":
                    tmp = get_api("default")
                    send_data("widget_set ha_client text2 1 2 20 2 h 2 {" + str(tmp[0]) + "}")
                    send_data("widget_set ha_client text3 1 3 20 3 h 2 {Kernel: " + str(tmp[1]) + "}")
                    send_data("widget_set ha_client text4 1 4 20 4 h 2 {Up: " + str(calc_uptime(tmp[2])) + "}")               
                    time.sleep(0.1)
              elif do_widget == "ha_cpu":
                while do_screen == True and do_widget == "ha_cpu":
                    tmp = get_api("cpu")
#                    send_data("widget_set ha_cpu text 1 2 {" + centre_text("CPU: "+str(tmp)+"%", 20) + "}") # old cpu
                    send_data("widget_set ha_cpu text 1 2 {" + centre_text("CPU Load: "+str(tmp[0])+"% ", 20) + "}")
                    send_data("widget_set ha_cpu text3 1 3 {" + centre_text("CPU Temp: "+str(tmp[1])+"°C", 20) + "}")
                    time.sleep(0.1)
              elif do_widget == "ha_mem":
                while do_screen == True and do_widget == "ha_mem":
                    tmp = get_api("mem")
                    send_data("widget_set ha_mem text 1 2 {Memory used: " + str(tmp[0]) + "%}")
                    send_data("widget_set ha_mem text3 1 3 {MEM Used:  " + str(bytesto(tmp[1], 'm')) + "MB}")
                    send_data("widget_set ha_mem text4 1 4 {MEM Total: " + str(bytesto(tmp[2], 'm')) + "MB}")
                    time.sleep(0.1)
              elif "ha_sensor" in do_widget:  ## sensors: 0=value 1=name 2=last_update
                while do_screen == True and "ha_sensor" in do_widget:
                  screen_id = do_widget
                  sensor_id = ""
                  for s in sensors:
                    if debug: print("s0:"+str(s[0]) +" s1:"+str(s[1])+" s2:"+str(s[2]) )
                    ## match screen_id
                    if s[0] == screen_id:
                      sensor_id = s[1]
                      if s[2] != '':
                        sensor_name = s[2]
                      else:
                        sensor_name = ''
                      break
                  if sensor_id == "":
                    print("ERROR no sensor_id found for "+ screen_id)
                    break
                  tmp = get_api(screen_id)
#                  if sensor_name in locals():
#                  if sensor_name:
                  if sensor_name != '':
                    send_data("widget_set "+str(screen_id)+" text2 1 2 20 2 h 2 {" + centre_text(str(sensor_name), 20) + "}") ## friendly name
                  else:
                    send_data("widget_set "+str(screen_id)+" text2 1 2 20 2 h 2 {" + centre_text(str(tmp[1]), 20) + "}") ## friendly name
#                  send_data("widget_set "+str(screen_id)+" text2 1 2 20 2 h 2 {" + centre_text(str(tmp[1]), 20) + "}") ## friendly name
                  send_data("widget_set "+str(screen_id)+" text3 1 3 \"" + centre_text(str(tmp[0]), 20 ) +"\"") ## state # double quote for special chars?
                  send_data("widget_set "+str(screen_id)+' text4 1 4 \"' + centre_text(""+ last_update(tmp[2]) +" ago", 20) + '\"') ## last updated
                  time.sleep(0.1)
              elif do_widget == "ha_net":
#                    tmp = get_api("net")
                    send_data("widget_set ha_net text 1 2 {"+ centre_text("network", 20) +"}")
                    send_data("widget_set ha_net text3 1 3 {"+ centre_text("coming soon", 20) +"}")
              elif do_widget == "ha_disk":
                while do_screen == True and do_widget == "ha_disk":
                    tmp = get_api("disk")
                    send_data("widget_set ha_disk text 1 2 {" + centre_text(str(tmp[0])+"% Free", 20) +"}")
                    send_data("widget_set ha_disk text3 1 3 {Used: " + str(tmp[1]) + "/"+str(tmp[2])+" GB}")
                    time.sleep(0.1)
              else:
                while do_screen == True:
                    print("Error: unknown widget while screen running: ", do_widget)
                    time.sleep(1)


## exit handler
## TODO
def exit_handler():
    print("LCDproc Client is ending!")

atexit.register(exit_handler)


#Attempt connection to server
try:
    sock.connect((jdata['lcdproc_host'], jdata['lcdproc_port']))
except:
    print("Could not make a connection to the server")
    sys.exit(0)
print("Connected to ", jdata['lcdproc_host'])

sock.send(b"hello\n")
data = sock.recv(128)
if debug: print(str(data.decode("utf-8")))

## decode hello string
pattern = re.compile("^connect\sLCDproc\s(\d\.\d\.\d)\sprotocol\s(\d\.\d)\slcd\swid\s(\d+)\shgt\s(\d+)\scellwid\s(\d)\scellhgt\s(\d)\n$")
m = pattern.match(data.decode("utf-8"))
if m:
  if debug:
    print(m.groups())
    print("LCDproc version: ", m.group(1))
    print("LCDproc protocol: ", m.group(2))
    print("LCDproc lcd width: ", m.group(3))
    print("LCDproc lcd height: ", m.group(4))
    print("LCDproc cell width: ", m.group(5))
    print("LCDproc cell height: ", m.group(6))
  sys_var['version'] = m.group(1)
  sys_var['protocol'] = m.group(2)
  sys_var['wid'] = m.group(3)
  sys_var['hgt'] = m.group(4)
  sys_var['cellwid'] = m.group(5)
  sys_var['cellhgt'] = m.group(6)
else:
  print("ERROR determing LCDproc server specs!")
  print("Server said: ", data.decode("utf-8") )
  print("Bailing out...")
  sys.exit(0)
  
print("Found LCDproc Server OK")
print("Server version:"+sys_var['version'] +" protocol:"+sys_var['protocol'] )
print("LCD Display size: "+sys_var['wid']+"x"+sys_var['hgt']+" [cell size: "+sys_var['cellwid']+"x"+sys_var['cellhgt']+"]" )

  
#### setup lcd screen(s)
send_data("client_set name {ha_client}")

## optional screens
if jdata['show_default'] == True:
  send_data("screen_add ha_client")
  send_data("screen_set ha_client name {HA Client}")
  send_data("widget_add ha_client title title")
  send_data("widget_set ha_client title {HA Client}")
  send_data("widget_add ha_client text2 scroller")
  send_data("widget_add ha_client text3 scroller")
  send_data("widget_add ha_client text4 scroller")
if jdata['show_cpu'] == True:
  send_data("screen_add ha_cpu")
  send_data("screen_set ha_cpu name {HA CPU %}")
  send_data("widget_add ha_cpu title title")
  send_data("widget_set ha_cpu title {HA CPU %}")
  send_data("widget_add ha_cpu text string")
  send_data("widget_set ha_cpu text 1 2 {default cpu txt}")
  send_data("widget_add ha_cpu text3 string")
if jdata['show_mem'] == True:
  send_data("screen_add ha_mem")
  send_data("screen_set ha_mem name {HA MEM %}")
  send_data("widget_add ha_mem title title")
  send_data("widget_set ha_mem title {HA MEM %}")
  send_data("widget_add ha_mem text string")
  send_data("widget_set ha_mem text 1 2 {default mem txt}")
  send_data("widget_add ha_mem text3 string")
  send_data("widget_add ha_mem text4 string")
if jdata['show_net'] == True:
  send_data("screen_add ha_net")
  send_data("screen_set ha_net name {HA NET}")
  send_data("widget_add ha_net title title")
  send_data("widget_set ha_net title {HA NET}")
  send_data("widget_add ha_net text string")
  send_data("widget_set ha_net text 1 2 {default net txt}")
  send_data("widget_add ha_net text3 string")
  send_data("widget_add ha_net text4 string")
if jdata['show_disk'] == True:
  send_data("screen_add ha_disk")
  send_data("screen_set ha_disk name {HA Disk %}")
  send_data("widget_add ha_disk title title")
  send_data("widget_set ha_disk title {HA Disk}")
  send_data("widget_add ha_disk text string")
  send_data("widget_set ha_disk text 1 2 {default disk txt}")
  send_data("widget_add ha_disk text3 string")
  send_data("widget_add ha_disk text4 string")

## build array of sensors to show, create screens for each
if jdata['show_sensors'] == True and jdata['list_sensors'] != "":
  print("Building sensors list:")

  if debug: print("list_sensors: [", jdata['list_sensors'], "]")
  cnt = 0
  for x in jdata['list_sensors']:
    if debug: print("adding sensor: ", x)
  # does have optional name?

    m = re.compile("^(\w+\.\w+)\s\"([\w\s]+)\"$").match(x)
    if m:
      sensors.append(["ha_sensor"+str(cnt), m.group(1), m.group(2) ])
      if debug: print("sensor: ", m.group(1) )
      if debug: print("name: ", m.group(2) )
    else:
      if debug: print("no name sensor: ", x )
      sensors.append(["ha_sensor"+str(cnt), x, ''])
    send_data("screen_add ha_sensor"+str(cnt))
    send_data("screen_set ha_sensor"+str(cnt)+" name {HA Sensor"+str(cnt)+"}")
    send_data("widget_add ha_sensor"+str(cnt)+" title title")
    send_data("widget_set ha_sensor"+str(cnt)+" title {HA Sensor"+str(cnt)+"}")
    send_data("widget_add ha_sensor"+str(cnt)+" text2 scroller")
    send_data("widget_add ha_sensor"+str(cnt)+" text3 string")
    send_data("widget_add ha_sensor"+str(cnt)+" text4 string")
    send_data("widget_set ha_sensor"+str(cnt)+" text3 1 2 {default sensor"+str(cnt)+" txt}")
    cnt = cnt + 1

  print("size of sensors: ", len(sensors) )
  print("sensors dump:")
  for x in sensors:
    print("s_dump screen_id:"+ str(x[0]) +" sensor_id:"+ str(x[1]) +" name:"+ str(x[2]) )


  if debug:
    print("size of sensors: ", len(sensors) )
    print("sensors dump:")
    for x in sensors:
      print("s_dump screen_id:"+ str(x[0]) +" sensor_id:"+ str(x[1]) +" name:"+ str(x[2]) )
else:
  print("sensors not enable OR list is empty")

  
print("starting threads....")
#Create new thread(s) to wait for data
receiveThread.start()

screenThread = threading.Thread(target = run_screen, args = () )
screenThread.start()


print ("Running!")


