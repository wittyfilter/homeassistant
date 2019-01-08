import os, io
from subprocess import call
import requests
import base64
import yaml
import homeassistant.remote as remote

with open("/home/pi/.homeassistant/secrets.yaml", 'r') as secrets:
  secret = yaml.load(secrets)
  apikey_baidu = secret['baidu_body_apikey']
  secretkey_baidu = secret['baidu_body_secretkey']
  ha_api = secret['http_password']
  ffmpeg_input = secret['ffmpeg_input']

timeout = 10
api = remote.API('127.0.0.1', ha_api)
domain = 'tts'
entity_id = 'media_player.vlc'
message1 = "欢迎你们"
message2 = "欢迎淡淡"
message3 = "欢迎哲哥"
message4 = "欢迎回家"

host_baidu_token = 'https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials'
token_baidu = requests.post(host_baidu_token, data={'client_id':apikey_baidu, 'client_secret':secretkey_baidu}).json()

# result = requests.post('https://open.ys7.com/api/lapp/device/capture', data={'accessToken':'','deviceSerial':'','channelNo':1}).json()
# if (result['code']=='200'):
#   imgurl = result['data']['picUrl']
# else:
#   imgurl = ''
# base64_data = base64.b64encode(io.BytesIO(requests.get(imgurl).content).read())

call(["ffmpeg", "-i", ffmpeg_input, "-f", "image2", "-t", "0.001", "-y", "/home/pi/tmpimg/snapshot.jpg"])
with open("/home/pi/tmpimg/snapshot.jpg", "rb") as f:
  base64_data = base64.b64encode(f.read())

host_baidu_body = 'https://aip.baidubce.com/rest/2.0/image-classify/v1/body_attr'
result = requests.post(host_baidu_body, data={'access_token':token_baidu['access_token'],'image':base64_data, 'type': 'gender,age,glasses'}).json()

while result['person_num'] == 0:
  call(["ffmpeg", "-i", ffmpeg_input, "-f", "image2", "-t", "0.001", "-y", "/home/pi/tmpimg/snapshot.jpg"])
  with open("/home/pi/tmpimg/snapshot.jpg", "rb") as f:
    base64_data = base64.b64encode(f.read())
  result = requests.post(host_baidu_body, data={'access_token':token_baidu['access_token'],'image':base64_data, 'type': 'gender,age,glasses'}).json()
  timeout = timeout-1
  if timeout == 0:
  	quit()

if result['person_num'] > 1:
  remote.call_service(api, domain, 'baidu_say', {'entity_id': entity_id, 'message': message1})
elif result['person_info'][0]['attributes']['gender']['score'] < 0.75:
  remote.call_service(api, domain, 'baidu_say', {'entity_id': entity_id, 'message': message4})
elif result['person_info'][0]['attributes']['gender']['name'] == "女性":
  remote.call_service(api, domain, 'baidu_say', {'entity_id': entity_id, 'message': message2})
else:
  remote.call_service(api, domain, 'baidu_say', {'entity_id': entity_id, 'message': message3})
