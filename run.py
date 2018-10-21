#!/usr/bin/env python3
# -*- encoding=utf-8 -*-
import argparse
import sched
import time
from cloud_music import CloudMusicApi, OSXLogger
from configobj import ConfigObj


def listen(song=None, start_play_time=0, play_time=0):
    """
    听一首歌
    :param dict song: 歌曲
    :param int start_play_time: 开始听时间
    :param int play_time: 共听了的时间
    """
    current_time = int(time.time() * 1000)  # 开始播放时间
    if song is not None:
        cloud_music_logger.play(song['id'],
                                song['artists'][0]['id'],
                                play_time,
                                'privilege' in song and song['privilege']['fee'] or 0,
                                'userfm',
                                start_play_time,
                                alg=song['alg'])
        write_log('《听了一首》%s' % song['name'])

    song = next(song_generator)
    if int(args.play_time) <= 0:
        play_time = int(song['duration'] / 1000)
    else:
        play_time = int(args.play_time)
    # 真的拉歌曲地址
    cloud_music_api.player_url((str(song['id']),))
    s.enter(play_time, 0, listen, (song, current_time, play_time))


def gen_song():
    """
    通过私人FM列表获取歌曲
    :return Generator:
    """
    while True:
        radio_list = cloud_music_api.radio_get()
        write_log('获得了%d首歌' % len(radio_list))
        for song in radio_list:
            yield song


def logger():
    """
    上报日志
    """
    log = cloud_music_logger.flush()
    resp = cloud_music_api.osx_log(log)
    if resp:
        cfg['logger']['seq'] = cloud_music_logger.get_seq()
        cfg.write()
    write_log('上报了一次日志,' + (resp and '成功' or '失败'))
    s.enter(600, 0, logger)  # 每10分钟上报一次日志


def write_log(log):
    """
    打日志
    :param str log:
    """
    print('[%s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), log))


if __name__ == '__main__':
    arg_parser = argparse.ArgumentParser('网易云音乐日志发送工具')
    group = arg_parser.add_argument_group('登录账号', '暂时只支持邮箱登录')
    group.add_argument('--username', '-u', help='用户名')
    group.add_argument('--password', '-p', help='密码')
    arg_parser.add_argument('--cookie', help='Cookie登录，只需要MUSIC_U')
    arg_parser.add_argument('--play_time', '-t', default=0, help='每首歌播放时间，0则播放整首歌')
    args = arg_parser.parse_args()

    cfg = ConfigObj('config.ini')

    cloud_music_api = CloudMusicApi()
    user_info = cloud_music_api.user_info()
    # 判断是否已登录过
    if user_info['code'] != 200:
        # 邮箱登录
        if args.username is not None and args.password is not None:
            cloud_music_api.login(args.username, args.password, 0)
        # Cookie登录
        elif args.cookie is not None:
            cloud_music_api.set_music_u(args.cookie)
        else:
            print('cookie登录或邮箱登录需要选择一种，更多请看-h')
            exit(1)
        user_info = cloud_music_api.user_info()
    # 获取用户ID
    if 'userPoint' in user_info and 'userId' in user_info['userPoint']:
        cloud_music_api.set_user_id(user_info['userPoint']['userId'])
    else:
        print('登录失败')
        exit(1)
    seq = cfg['logger']['seq']
    cloud_music_logger = OSXLogger(seq)
    # 使用shced调度听歌和上传日志
    s = sched.scheduler()
    song_generator = gen_song()
    s.enter(0, 0, listen)
    s.enter(600, 0, logger)
    s.run()
