# -*- encoding=utf-8 -*-
import hashlib
import io
import json
import math
import pickle
import random
import time
import urllib3
import uuid
from Crypto.Cipher import AES
from binascii import b2a_hex
from urllib import parse
from zip import Zip


class CloudMusicApi:
    """
    网易云音乐API调用
    """
    _default_headers = {
        'Accept': '*/*',
        'Origin': 'orpheus://orpheus',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko)',
        'Accept-language': 'zh-cn',
        'Accept-encoding': 'gzip, deflate',
    }
    _user_id = 0

    def __init__(self, num_pools=10, proxy=None):
        """初始化urllib
        :param int num_pools: 线程数量
        :param str proxy: 代理地址
        """
        self._cookie = Cookie(default_cookie={
            'appver': '1.5.9',
            'channel': 'netease',
            'os': 'osx',
            'osver': '版本 10.13.6（版号 17G65）',
        })
        # 若没有deviceId则生成一个
        if self._cookie.get_cookie('deviceId') is None:
            self._cookie['deviceId'] = generate_device_id()
        # 禁用https不安全警告
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        if proxy is None:
            self.__http_pool = urllib3.PoolManager(num_pools, self._default_headers)
        else:
            self.__http_pool = urllib3.ProxyManager(proxy, num_pools, self._default_headers)

    def login(self, username, password, login_type):
        m = hashlib.md5()
        m.update(password.encode())
        params = {
            'username': username,
            'password': m.hexdigest(),
            'type': str(login_type),
            'remember': 'true',
            'https': 'true',
            'e_r': True,
        }
        resp = self._request_eapi('/eapi/login', b'/api/login', params, True)
        if resp is not None and resp['code'] == 200:
            return {
                'account': resp['account'],
                'profile': resp['profile'],
            }
        return None

    def refresh_token(self):
        """
        cookie续命
        :return bool: 是否刷新成功
        """
        music_u = self._cookie.get_cookie('MUSIC_U')
        if music_u is None:
            return False
        params = {
            'cookieToken': music_u,
        }
        resp = self._request_eapi('/eapi/login/token/refresh', b'/api/login/token/refresh', params)
        if resp is not None and resp['code'] == 200:
            return True
        else:
            return False

    def user_info(self):
        """
        获取用户信息
        :return dict:
        """
        resp = self._request_eapi('/eapi/v1/user/info', b'/api/v1/user/info', {})
        return resp

    def radio_get(self):
        """
        获取私人fm列表
        :return list|None: 歌曲列表
        """
        resp = self._request_eapi('/eapi/v1/radio/get', b'/api/v1/radio/get', {})
        if resp is not None and resp['code'] == 200:
            return resp['data']
        else:
            return None

    def player_url(self, song_ids, br=320000):
        """
        获取播放地址
        :param tuple(str) song_ids: 歌曲ID列表
        :param int br: 歌曲码率
        :return dict:
        """
        params = {
            'ids': json.dumps(song_ids, separators=(',', ':')),
            'br': str(br),
            'e_r': True
        }
        resp = self._request_eapi('/eapi/song/enhance/player/url', b'/api/song/enhance/player/url', params, True)
        if resp is not None and resp['code'] == 200:
            return resp['data']
        return None

    def batch(self, api_params):
        """
        批量请求api
        :param dict api_params: API列表及请求参数
            如dict(
                '/api/discovery/hotspot': json.dumps({'limit' : 12}),
                '/api/discovery/recommend/resource': json.dumps({'limit': 3}),
            )
        :return dict: 请求结果
        """
        return self._request_eapi('/eapi/batch', b'/batch', api_params)

    def set_music_u(self, music_u):
        """
        设置登录Cookie
        :param str music_u:
        """
        self._cookie['MUSIC_U'] = music_u

    def set_user_id(self, user_id):
        """
        设置当前用户ID
        :param int user_id:
        """
        self._user_id = user_id

    def osx_log(self, log_data):
        """
        发送OSX客户端的日志
        :param bytes log_data: 日志记录数据
        :return bool: 是否发送成功
        """
        url = 'http://music.163.com/api/feedback/client/log'
        music_u = self._cookie.get_cookie('MUSIC_U')
        if music_u is not None:
            url += '?MUSIC_U=' + music_u
        file_name = time.strftime(str(self._user_id) + '_%Y-%m-%d %H:%M:%S.log')
        # 压缩日志
        zip_data = Zip.compress_data({
            file_name: log_data
        })
        resp = self._request('POST', url, {'attach': ('%dlog.zip' % self._user_id, zip_data)})
        if resp is not None:
            data = json.loads(resp.data.decode())
            return data['code'] == 200
        return False

    def _request_eapi(self, gateway_path, request_path, params, decrpyt=False):
        """
        请求eapi并获取返回结果
        :param str gateway_path: 请求网关的路径
        :param bytes request_path: 请求后端的路径
        :param dict params: 请求参数，会自动进行加密处理
        :return dict: 请求结果
        """
        params['verifyId'] = 1
        params['os'] = 'OSX'
        params['header'] = json.dumps({
            'os': 'osx',
            'appver': '1.5.9',
            'requestId': str(random.randint(10000000, 99999999)),
            'clientSign': '',
        }, separators=(',', ':'))
        params = self._eapi_encrypt(request_path, params)
        url = 'https://music.163.com' + gateway_path
        resp = self._request('POST', url, {'params': params}, encode_multipart=False)
        if resp is None:
            return None
        else:
            if decrpyt:
                data = self._eapi_decrypt(resp.data)
            else:
                data = resp.data
            return json.loads(data.decode())

    @staticmethod
    def _eapi_encrypt(path, params):
        """eapi
        接口参数加密
        :param bytes path: 请求的路径
        :param params: 请求参数
        :return str: 加密结果
        """
        params = json.dumps(params, separators=(',', ':')).encode()
        sign_src = b'nobody' + path + b'use' + params + b'md5forencrypt'
        m = hashlib.md5()
        m.update(sign_src)
        sign = m.hexdigest()
        aes_src = path + b'-36cd479b6b5-' + params + b'-36cd479b6b5-' + sign.encode()
        pad = 16 - len(aes_src) % 16
        aes_src = aes_src + bytearray([pad] * pad)
        crypt = AES.new(b'e82ckenh8dichen8', AES.MODE_ECB)
        ret = crypt.encrypt(aes_src)
        return b2a_hex(ret).upper()

    @staticmethod
    def _eapi_decrypt(data):
        """
        解密eapi返回结果
        :param bytes data: 密文
        :return bytes: 原文
        """
        crypt = AES.new(b'e82ckenh8dichen8', AES.MODE_ECB)
        data = crypt.decrypt(data)
        pad = ord(data[-1:])
        if 1 <= pad <= 16:
            data = data[:-pad]
        return data

    def _request(self, method, url, data, **urlopenkw):
        """
        发起HTTP请求
        :param string method: 请求method
        :param string url: 请求地址
        :param dict|None data: 请求的body
        :param urlopenkw: urlopen的参数
        :return bytes: 请求结果
        """
        headers = self._default_headers
        headers['Cookie'] = self._cookie.get_cookie()
        resp = self.__http_pool.request(method, url, data, headers, **urlopenkw)
        self._cookie.set_cookie(resp.headers.getlist('set-cookie'))
        if resp.status == 200:
            return resp
        else:
            return None


class Cookie:
    """
    定制的高端Cookie处理
    """

    def __init__(self, save_path='./.cookie', default_cookie=None):
        self._save_path = save_path
        try:
            with open(save_path, 'rb') as fp:
                self._cookie = pickle.load(fp)
                self._cookie = dict(default_cookie, **self._cookie)
        except (EOFError, FileNotFoundError):
            self._cookie = default_cookie and default_cookie or {}

    def __setitem__(self, key, value):
        self._cookie[key] = value

    def get_cookie(self, name=None):
        """
        获取单个cookie或所有cookie
        :param str name: Cookie名
        :return str: Cookie内容
        """
        if name is None:
            return parse.urlencode(self._cookie).replace('&', ';')
        else:
            if name in self._cookie:
                return self._cookie[name]
            else:
                return None

    def set_cookie(self, cookies):
        """
        解析header中set-cookie的内容并保存持久化
        :param tuple(str) cookies: header中set-cookie的内容
        """
        if len(cookies) == 0:
            return
        for cookie in cookies:
            cookie = cookie.split(';', 1)
            cookie = cookie[0].split('=', 1)
            if len(cookie) == 2:
                self._cookie[cookie[0]] = cookie[1]
        with open(self._save_path, 'wb') as fp:
            pickle.dump(self._cookie, fp)


class Logger:
    """
    日志记录
    """

    def __init__(self, seq=1):
        self._buffer = io.BytesIO()
        self._seq = int(seq)
        # 如果设备是第一次记录，则需要发送active
        if self._seq <= 1:
            self.write('active', {'source': 'netease'})
            self._seq = 2

    def __del__(self):
        if self._buffer is not None:
            self._buffer.close()

    def write(self, log_type, params, log_time=None):
        """
        记录一条日志
        :param str log_type: 日志类型
        :param dict params: 日志记录内容
        :param str|int|None log_time: 日志时间戳
        """
        params['seq'] = self._seq
        if log_time is None:
            log_time = int(time.time())
        self._buffer.write(str(log_time).encode())
        self._buffer.write(b'\x01')
        self._buffer.write(log_type.encode())
        self._buffer.write(b'\x01')
        self._buffer.write(json.dumps(params, separators=(',', ':')).encode())
        self._buffer.write(b'\x0A\x0A')
        self._seq += 1

    def flush(self):
        """
        获取输出的日志并清空缓冲区
        :return bytes:输出的日志
        """
        ret = self._buffer.getvalue()
        self._buffer.close()
        self._buffer = io.BytesIO()
        return ret

    def get_seq(self):
        """
        获取当前日志序号
        :return int:
        """
        return self._seq


class OSXLogger(Logger):
    """
    OSX的日志记录
    """

    def play(self, song_id, artist_id, play_time, fee, source, start_play_time=None, **kw):
        """
        记录播放日志
        :param int song_id: 歌曲ID
        :param int artist_id: 歌唱家ID(多个只取第一个)
        :param int play_time: 播放时间
        :param int fee: 歌曲下载费用
        :param str source: 歌曲来源,如userfm,list
        :param int start_play_time: 开始播放的时间戳(ms)
        :param kw: 其余参数
            source='userfm',需要传alg
            source='list',需要传sourceId
        """
        if play_time is None:
            play_time = int(time.time() * 1000)
        params = {
            'type': 'song',
            'id': song_id,
            'time': play_time,
            'network': 1,
            'artistid': artist_id,
            'download': 0,
            'end': 'playend',
            'source': source,
            'bitrate': 128,
            'startlogtime': start_play_time,
            'status': 'back',
            'fee': fee,
        }
        if len(kw) > 0:
            params = dict(params, **kw)
        log_time = int(math.ceil(start_play_time / 1000)) + play_time
        self.write('play', params, log_time)


def generate_device_id():
    """
    生成deviceId
    :return str:
    """
    return ('%s|%s' % (uuid.uuid1(), uuid.uuid4())).upper()
