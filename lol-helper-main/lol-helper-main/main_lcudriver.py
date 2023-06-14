import threading
import time
import httpx
from pathlib import Path
from Enum.Structs import *
import datetime
from Enum.Enums import *
from lcu_driver import Connector
from loguru import logger
from modules.UserData import UserClass
import json

class LcuApi:
    def __init__(self):
        self.auth_token = None
        self.app_port = None
        self.url = None
        self.Clienturl = "127.0.0.1:2999"
        self.InitParam()
    def InitParam(self):
        self.app_port = 55693
        self.auth_token = "KQ17D0IGSe7HVJ29tbUr-A"
        self.url = f"https://127.0.0.1:{self.app_port}"  # riot:{self.auth_token}@
        self.auth = httpx.BasicAuth('riot', self.auth_token)
        self.header = {
            'Connection': 'keep-alive',
            'Accept': 'application/json',
            "Content-Type": "application/json"
            # "Authorization": self.token
        }
    async def doGet(self, route: str, http2: bool = False):
        """get请求"""
        async with httpx.AsyncClient(auth=self.auth, headers=self.header, verify=False, http2=http2) as client:
            req = await client.get(url=self.url + route)
            if req.status_code == 404:
                logger.error(f"[*]404 {req.json()['message']}  '{route}'")
            return req

    async def doPost(self, route: str, http2: bool = False, **kwargs):
        """post请求"""
        async with httpx.AsyncClient(auth=self.auth, headers=self.header, verify=False, http2=http2) as client:
            # if kwargs.get('data'):
            #     kwargs['data'] = json.dumps(kwargs['data'])
            req = await client.post(self.url + route, **kwargs)
            if req.status_code == 404:
                logger.error(f"[*]404 {req.json()['message']}  '{route}'")
            return req

    async def doDelete(self, route: str):
        """delete请求"""
        async with httpx.AsyncClient(auth=self.auth, headers=self.header, verify=False) as client:
            req = await client.delete(url=self.url + route)
            if req.status_code == 404:
                logger.error(f"[*]404 {req.json()['message']}  '{route}'")
            return req

    async def doPut(self, route: str, data: dict = None):
        """put请求"""
        async with httpx.AsyncClient(auth=self.auth, headers=self.header, verify=False) as client:
            req = await client.put(url=self.url + route, json=data)
            if req.status_code == 404:
                logger.error(f"[*]404 {req.json()['message']}  '{route}'")
            return req

    async def doPatch(self, route: str, data: dict = None):
        """patch请求"""
        async with httpx.AsyncClient(auth=self.auth, headers=self.header, verify=False) as client:
            req = await client.patch(url=self.url + route, json=data)
            if req.status_code == 404:
                logger.error(f"[*]404 {req.json()['message']}  '{route}'")
            return req
    async def GetEnvironment(self) -> str:
        """获取玩家大区"""
        environment = (await self.doGet(ROUTE.environment)).json()['environment']
        return Environment[environment]
    async def GetUserInfo(self) -> SummonerInfo:
        """
        获取英雄信息
        """
        req = (await self.doGet(ROUTE.current_summoner)).json()
        env = await self.GetEnvironment()
        summoner = SummonerInfo(req['summonerId'], req['displayName'], req['puuid'], req['summonerLevel'],
                                req['profileIconId'], env)
        logger.info(f"当前用户: {summoner.displayName}")
        logger.info(f"服务器: {summoner.environment}")
        return summoner

    async def GetTeamUser(self):
        team = (await self.doGet(ROUTE.BpSession)).json()['myTeam']
        return team

    async def GetInfoById(self, id: str):
        """summoner_id查找玩家"""
        req = (await self.doGet(ROUTE.summoner_by_puuid.format(id))).json()
        return SummonerInfo(req['summonerId'], req['displayName'], req['puuid'], req['summonerLevel'])

    async def GetRankList(self, puuid: str = None):
        """通过id、puuid查找对局记录"""
        matchs = (await self.doGet(ROUTE.match_list_by_puuid.format(puuid))).json()
        return matchs
    async def GetRankScore(self, puuid: str = None):
        """获取kda"""
        count = 10
        data = await self.GetRankList(puuid)
        rank_list = []
        if len(data['games']['games']) < count:
            count = len(data['games']['games'])
        ranks = data['games']['games']
        for i in range(count):
            start_time = datetime.datetime.strptime(ranks[i]['gameCreationDate'][:19],
                                                    '%Y-%m-%dT%H:%M:%S')
            start_time = start_time + datetime.timedelta(hours=8)
            start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
            champion_name = (await self.doGet(ROUTE.grid_champions.format(ranks[i]['participants'][0]['championId']))).json()['name']
            stats = ranks[i]['participants'][0]['stats']
            rank_list.append({
                "start_time": start_time,
                "champion_name": champion_name,
                "kills": stats['kills'],
                "deaths": stats['deaths'],
                "assists": stats['assists'],
            })
        return rank_list

connector = Connector()
api = LcuApi()
user = UserClass()


@connector.ready
async def connect(connection):
    user_info = (await connection.request('get', ROUTE.current_summoner)).json()
    environment = Environment[(await connection.request('get', ROUTE.environment)).json()['environment']]
    user.info = await api.GetUserInfo()
    print(f"玩家登陆:\n"
          f"名字:{user.info.displayName}\n"
          f"服务器:{user.info.environment}\n"
          f"等级:{user.info.summonerLevel}\n"
          f"summonerId:{user.info.summonerId}\n"
          f"puuid:{user.info.puuid}")


@connector.close
async def disconnect(_):
    await connector.stop()


@connector.ws.register(ROUTE.session, event_types=('UPDATE',))
async def _(connection, event):
    data = event.data
    if data['phase'] == StateEvent.Champselect:
        user.gamemode = data["gameData"]["queue"]["type"]


@connector.ws.register(ROUTE.game_flow, event_types=('UPDATE',))
async def _(connection, event):
    status = event.data
    if status == StateEvent.Champselect:
        users = await api.GetTeamUser()
        logger.info(f"当前队伍人数：{len(users)}")
        time.sleep(1)
        text = ""
        for i in users:
            summonerId = i['puuid']
            display_name = (await api.GetInfoById(summonerId)).displayName
            source = await api.GetRankScore(summonerId)
            t = "玩家：" + display_name + "\n"
            for sou in source:
                kill = sou['kills']
                assist = sou['assists']
                death = sou['deaths']
                true_death = 1 if death == 0 else death
                kda = (kill + assist) / true_death*3
                t += "开始时间：" + str(sou['start_time']) + " " + sou['champion_name'] + " " + str(kill) + "/" + str(death) + "/" + str(assistpp) + " " + str(kda) + "\n"
        print(text)
    elif status == StateEvent.InProgress:
        pass
    elif status == StateEvent.EndOfGame:
        pass


@connector.ws.register(ROUTE.current_rune, event_types=('UPDATE',))
async def _(connection, event):
    pass
    # if not info.runed and event.data['isActive']:
    #     info.runed = True
    #     await api.SetRune(info.current_champion)

#threading.Thread(target=connector.start).start()
connector.start()
