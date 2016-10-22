# -*- coding: UTF-8 -*-
#===============================================================================
# Copyright (C) 2010 Diego Duclos
#
# This file is part of pyfa.
#
# pyfa is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyfa is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyfa.  If not, see <http://www.gnu.org/licenses/>.
#===============================================================================

import re
import threading
import wx

import Queue

import config
import eos.db
import eos.types
from sqlalchemy.sql import and_, or_
from service.settings import SettingsProvider, NetworkSettings
import service
import service.conversions as conversions
import logging

try:
    from collections import OrderedDict
except ImportError:
    from utils.compat import OrderedDict

logger = logging.getLogger(__name__)

# Event which tells threads dependent on Market that it's initialized
mktRdy = threading.Event()

class ShipBrowserWorkerThread(threading.Thread):
    def run(self):
        self.queue = Queue.Queue()
        self.cache = {}
        # Wait for full market initialization (otherwise there's high risky
        # this thread will attempt to init Market which is already being inited)
        mktRdy.wait(5)
        self.processRequests()

    def processRequests(self):
        queue = self.queue
        cache = self.cache
        sMkt = Market.getInstance()
        while True:
            try:
                id, callback = queue.get()
                set = cache.get(id)
                if set is None:
                    set = sMkt.getShipList(id)
                    cache[id] = set

                wx.CallAfter(callback, (id, set))
            except:
                pass
            finally:
                try:
                    queue.task_done()
                except:
                    pass

class PriceWorkerThread(threading.Thread):
    def run(self):
        self.queue = Queue.Queue()
        self.wait = {}
        self.processUpdates()

    def processUpdates(self):
        queue = self.queue
        while True:
            # Grab our data
            callback, requests = queue.get()

            # Grab prices, this is the time-consuming part
            if len(requests) > 0:
                service.Price.fetchPrices(requests)

            wx.CallAfter(callback)
            queue.task_done()

            # After we fetch prices, go through the list of waiting items and call their callbacks
            for price in requests:
                callbacks = self.wait.pop(price.typeID, None)
                if callbacks:
                    for callback in callbacks:
                        wx.CallAfter(callback)

    def trigger(self, prices, callbacks):
        self.queue.put((callbacks, prices))

    def setToWait(self, itemID, callback):
        if itemID not in self.wait:
            self.wait[itemID] = []
        self.wait[itemID].append(callback)

class SearchWorkerThread(threading.Thread):
    def run(self):
        self.cv = threading.Condition()
        self.searchRequest = None
        self.processSearches()

    def processSearches(self):
        cv = self.cv

        while True:
            cv.acquire()
            while self.searchRequest is None:
                cv.wait()

            request, callback, filterOn = self.searchRequest
            self.searchRequest = None
            cv.release()
            sMkt = Market.getInstance()
            if filterOn is True:
                # Rely on category data provided by eos as we don't hardcode them much in service
                filter = or_(eos.types.Category.name.in_(sMkt.SEARCH_CATEGORIES), eos.types.Group.name.in_(sMkt.SEARCH_GROUPS))
            elif filterOn:  # filter by selected categories
                filter = eos.types.Category.name.in_(filterOn)
            else:
                filter=None

            results = eos.db.searchItems(request, where=filter,
                                         join=(eos.types.Item.group, eos.types.Group.category),
                                         eager=("icon", "group.category", "metaGroup", "metaGroup.parent"))

            items = set()
            # Return only published items, consult with Market service this time
            for item in results:
                if sMkt.getPublicityByItem(item):
                    items.add(item)
            wx.CallAfter(callback, items)

    def scheduleSearch(self, text, callback, filterOn=True):
        self.cv.acquire()
        self.searchRequest = (text, callback, filterOn)
        self.cv.notify()
        self.cv.release()

class Market():
    instance = None
    def __init__(self):
        self.priceCache = {}

        #Init recently used module storage
        serviceMarketRecentlyUsedModules = {"pyfaMarketRecentlyUsedModules": []}

        self.serviceMarketRecentlyUsedModules = SettingsProvider.getInstance().getSettings("pyfaMarketRecentlyUsedModules", serviceMarketRecentlyUsedModules)

        # Start price fetcher
        self.priceWorkerThread = PriceWorkerThread()
        self.priceWorkerThread.daemon = True
        self.priceWorkerThread.start()

        # Thread which handles search
        self.searchWorkerThread = SearchWorkerThread()
        self.searchWorkerThread.daemon = True
        self.searchWorkerThread.start()

        # Ship browser helper thread
        self.shipBrowserWorkerThread = ShipBrowserWorkerThread()
        self.shipBrowserWorkerThread.daemon = True
        self.shipBrowserWorkerThread.start()

        # Items' group overrides
        self.customGroups = set()
        # Limited edition ships
        self.les_grp = eos.types.Group()
        self.les_grp.ID = -1
        self.les_grp.name = "特别版舰船"
        self.les_grp.published = True
        ships = self.getCategory("舰船")
        self.les_grp.category = ships
        self.les_grp.categoryID = ships.ID
        self.les_grp.description = ""
        self.les_grp.icon = None
        self.ITEMS_FORCEGROUP = {
            "奥普克斯级豪华游轮": self.les_grp, # One of those is wedding present at CCP fanfest, another was hijacked from ISD guy during an event
            "白银富豪级": self.les_grp,  # Amarr Championship prize
            "黄金富豪级": self.les_grp,  # Amarr Championship prize
            "末日沙场级帝国型": self.les_grp,  # Amarr Championship prize
            "灾难级帝国型": self.les_grp, # Amarr Championship prize
            "狂怒守卫者级": self.les_grp, # Illegal rewards for the Gallente Frontier Tour Lines event arc
            "万王宝座级联邦型": self.les_grp, # Reward during Crielere event
            "乌鸦级政府型": self.les_grp,  # AT4 prize
            "狂暴级部族型": self.les_grp, # AT4 prize
            "神圣穿梭机": self.les_grp, # 5th EVE anniversary present
            "微风级": self.les_grp, # 2010 new year gift
            "元始级": self.les_grp, # Promotion of planetary interaction
            "暴狼级": self.les_grp, # AT7 prize
            "弥米尔级": self.les_grp, # AT7 prize
            "乌图级": self.les_grp, # AT8 prize
            "复仇女神级": self.les_grp, # AT8 prize
            "梯队级": self.les_grp, # 2011 new year gift
            "恶意级": self.les_grp, # AT9 prize
            "传道者级": self.les_grp, # AT9 prize
            "魔裔级": self.les_grp, # AT10 prize
            "伊塔那级": self.les_grp, # AT10 prize
            "克雷默斯级": self.les_grp, # AT11 prize :(
            "莫拉查级": self.les_grp, # AT11 prize
            "斯特修斯级应急反应型": self.les_grp, # Issued for Somer Blink lottery
            "米亚莫斯级酷菲特强版": self.les_grp, # Gift to people who purchased FF HD stream
            "星际捷运穿梭机": self.les_grp,
            "美洲豹级": self.les_grp, # 2013 new year gift
            "长尾蜥级": self.les_grp, # AT12 prize
            "变色龙级": self.les_grp, # AT12 prize
            "凯旋奢华游艇":  self.les_grp,  # Worlds Collide prize \o/ chinese getting owned
            "小鬼级": self.les_grp,  # AT13 prize
            "恶魔级": self.les_grp,  # AT13 prize
        }

        self.ITEMS_FORCEGROUP_R = self.__makeRevDict(self.ITEMS_FORCEGROUP)
        self.les_grp.addItems = list(self.getItem(itmn) for itmn in self.ITEMS_FORCEGROUP_R[self.les_grp])
        self.customGroups.add(self.les_grp)

        # List of items which are forcibly published or hidden
        self.ITEMS_FORCEPUBLISHED = {
            "数据破坏仪 I": False, # Not used in EVE, probably will appear with Dust link
            "QA Cross Protocol Analyzer": False, # QA modules used by CCP internally
            "QA测试伤害模块": False,
            "QA测试ECCM": False,
            "QA测试免疫装备": False,
            "QA测试多舰船模块 - 10个玩家": False,
            "QA测试多舰船模块 - 20个玩家": False,
            "QA测试多舰船模块 - 40个玩家": False,
            "QA测试多舰船模块 - 5个玩家": False,
            "QA测试远程装甲维修系统  - 5个玩家": False,
            "QA测试护盾传输装置 - 5个玩家": False,
            "高鲁的穿梭机": False,
            "古斯塔斯穿梭机": False,
            "移动式诱捕装置": False,  # Seems to be left over test mod for deployables
            "锦标赛微型跳跃装置": False,  # Normally seen only on tournament arenas
            "议会外交穿梭机": False,  # CSM X celebration
            "民用加特林磁轨炮": True,
            "民用加特林脉冲激光炮": True,
            "民用加特林自动加农炮": True,
            "民用轻型电子疾速炮": True,
        }

        # do not publish ships that we convert
        for name in conversions.packs['skinnedShips']:
            self.ITEMS_FORCEPUBLISHED[name] = False

        if config.debug:
            # Publish Tactical Dessy Modes if in debug
            # Cannot use GROUPS_FORCEPUBLISHED as this does not force items
            # within group to be published, but rather for the group itself
            # to show up on ship list
            group = self.getGroup("改装件", eager="items")
            for item in group.items:
                self.ITEMS_FORCEPUBLISHED[item.name] = True

        # List of groups which are forcibly published
        self.GROUPS_FORCEPUBLISHED = {
            "考察船原型": False } # We moved the only ship from this group to other group anyway

        # Dictionary of items with forced meta groups, uses following format:
        # Item name: (metagroup name, parent type name)
        self.ITEMS_FORCEDMETAGROUP = {
            "栖息采矿器 I": ("故事线", "采矿器 I"),
            "野性采矿器 I": ("故事线", "采矿器 I"),
            "中型纳米装甲维修组件 I": ("一级科技", "中型装甲维修器 I"),
            "大型回光外壳重塑装置 I": ("故事线", "大型装甲维修器 I"),
            "卡尼迪海军鱼雷发射器": ("势力", "鱼雷发射器 I"),}
        # Parent type name: set(item names)
        self.ITEMS_FORCEDMETAGROUP_R = {}
        for item, value in self.ITEMS_FORCEDMETAGROUP.items():
            parent = value[1]
            if not parent in self.ITEMS_FORCEDMETAGROUP_R:
                self.ITEMS_FORCEDMETAGROUP_R[parent] = set()
            self.ITEMS_FORCEDMETAGROUP_R[parent].add(item)
        # Dictionary of items with forced market group (service assumes they have no
        # market group assigned in db, otherwise they'll appear in both original and forced groups)
        self.ITEMS_FORCEDMARKETGROUP = {
            "阿尔法数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "法典数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "守护者数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "圣契数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "高级大脑加速器": 977, # Implants & Boosters > Booster
            "民用损伤控制": 615, # Ship Equipment > Hull & Armor > Damage Controls
            "民用电磁防护力场": 1695, # Ship Equipment > Shield > Shield Hardeners > EM Shield Hardeners
            "民用爆炸偏阻力场": 1694, # Ship Equipment > Shield > Shield Hardeners > Explosive Shield Hardeners
            "民用地精灵无人机": 837, # Drones > Combat Drones > Light Scout Drones
            "民用动能偏阻力场": 1693, # Ship Equipment > Shield > Shield Hardeners > Kinetic Shield Hardeners
            "民用轻型导弹发射器": 640, # Ship Equipment > Turrets & Bays > Missile Launchers > Light Missile Launchers
            "民用鞭挞轻型导弹": 920, # Ammunition & Charges > Missiles > Light Missiles > Standard Light Missiles
            "民用小型远程装甲维修器": 1059, # Ship Equipment > Hull & Armor > Remote Armor Repairers > Small
            "民用小型远程护盾回充增量器": 603, # Ship Equipment > Shield > Remote Shield Boosters > Small
            "民用停滞缠绕光束": 683, # Ship Equipment > Electronic Warfare > Stasis Webifiers
            "民用热能发散力场": 1692, # Ship Equipment > Shield > Shield Hardeners > Thermal Shield Hardeners
            "民用跃迁干扰器": 1935, # Ship Equipment > Electronic Warfare > Warp Disruptors
            "神经交互强化芯片—载诺 精确射击 ZMX10": 1493, # Implants & Boosters > Implants > Skill Hardwiring > Missile Implants > Implant Slot 06
            "神经交互强化芯片—载诺 精确射击 ZMX100": 1493, # Implants & Boosters > Implants > Skill Hardwiring > Missile Implants > Implant Slot 06
            "神经交互强化芯片—载诺 精确射击 ZMX1000": 1493, # Implants & Boosters > Implants > Skill Hardwiring > Missile Implants > Implant Slot 06
            "神经交互强化芯片—载诺 精确射击 ZMX11": 1493, # Implants & Boosters > Implants > Skill Hardwiring > Missile Implants > Implant Slot 06
            "神经交互强化芯片—载诺 精确射击 ZMX110": 1493, # Implants & Boosters > Implants > Skill Hardwiring > Missile Implants > Implant Slot 06
            "神经交互强化芯片—载诺 精确射击 ZMX1100": 1493, # Implants & Boosters > Implants > Skill Hardwiring > Missile Implants > Implant Slot 06
            "纳基维合成型蓝色药丸增效体": 977, # Implants & Boosters > Booster
            "实验级大脑加速器": 977, # Implants & Boosters > Booster
            "彩虹女神探针发射器原型机": 712, # Ship Equipment > Turrets & Bays > Scan Probe Launchers
            "暗影": 1310, # Drones > Combat Drones > Fighter Bombers
            "冬眠者数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "标准大脑加速器": 977, # Implants & Boosters > Booster
            "塔洛迦数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "地球人数据分析仪 I": 714, # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
            "特里蒙数据分析仪 I": 714  # Ship Equipment > Electronics and Sensor Upgrades > Scanners > Data and Composition Scanners
        }

        self.ITEMS_FORCEDMARKETGROUP_R = self.__makeRevDict(self.ITEMS_FORCEDMARKETGROUP)

        self.FORCEDMARKETGROUP = {
            685: False, # Ship Equipment > Electronic Warfare > ECCM
            681: False, # Ship Equipment > Electronic Warfare > Sensor Backup Arrays
        }

        # Misc definitions
        # 0 is for items w/o meta group
        self.META_MAP = OrderedDict([("normal",  frozenset((0, 1, 2, 14))),
                                     ("faction", frozenset((4, 3))),
                                     ("complex", frozenset((6,))),
                                     ("officer", frozenset((5,)))])
        self.SEARCH_CATEGORIES = ("无人机", "装备", "子系统", "弹药", "植入体", "可部署物品", "铁骑舰载机", "建筑", "建筑装备")
        self.SEARCH_GROUPS = ("冰矿产物",)
        self.ROOT_MARKET_GROUPS = (9,     # Modules
                                   1111,  # Rigs
                                   157,   # Drones
                                   11,    # Ammo
                                   1112,  # Subsystems
                                   24,    # Implants & Boosters
                                   404,   # Deployables
                                   2202,  # Structure Equipment
                                   2203   # Structure Modifications
                                   )
        # Tell other threads that Market is at their service
        mktRdy.set()

    @classmethod
    def getInstance(cls):
        if cls.instance == None:
            cls.instance = Market()
        return cls.instance

    def __makeRevDict(self, orig):
        """Creates reverse dictionary"""
        rev = {}
        for item, value in orig.items():
            if not value in rev:
                rev[value] = set()
            rev[value].add(item)
        return rev

    def getItem(self, identity, *args, **kwargs):
        """Get item by its ID or name"""
        try:
            if isinstance(identity, eos.types.Item):
                item = identity
            elif isinstance(identity, int):
                item = eos.db.getItem(identity, *args, **kwargs)
            elif isinstance(identity, basestring):
                # We normally lookup with string when we are using import/export
                # features. Check against overrides
                identity = conversions.all.get(identity, identity)
                item = eos.db.getItem(identity, *args, **kwargs)
            elif isinstance(identity, float):
                id = int(identity)
                item = eos.db.getItem(id, *args, **kwargs)
            else:
                raise TypeError("Need Item object, integer, float or string as argument")
        except:
            logger.error("Could not get item: %s", identity)
            raise

        return item

    def getGroup(self, identity, *args, **kwargs):
        """Get group by its ID or name"""
        if isinstance(identity, eos.types.Group):
            return identity
        elif isinstance(identity, (int, float, basestring)):
            if isinstance(identity, float):
                identity = int(identity)
            # Check custom groups
            for cgrp in self.customGroups:
                # During first comparison we need exact int, not float for matching
                if cgrp.ID == identity or cgrp.name == identity:
                    # Return first match
                    return cgrp
            # Return eos group if everything else returned nothing
            return eos.db.getGroup(identity, *args, **kwargs)
        else:
            raise TypeError("Need Group object, integer, float or string as argument")

    def getCategory(self, identity, *args, **kwargs):
        """Get category by its ID or name"""
        if isinstance(identity, eos.types.Category):
            category = identity
        elif isinstance(identity, (int, basestring)):
            category = eos.db.getCategory(identity, *args, **kwargs)
        elif isinstance(identity, float):
            id = int(identity)
            category = eos.db.getCategory(id, *args, **kwargs)
        else:
            raise TypeError("Need Category object, integer, float or string as argument")
        return category

    def getMetaGroup(self, identity, *args, **kwargs):
        """Get meta group by its ID or name"""
        if isinstance(identity, eos.types.MetaGroup):
            metaGroup = identity
        elif isinstance(identity, (int, basestring)):
            metaGroup = eos.db.getMetaGroup(identity, *args, **kwargs)
        elif isinstance(identity, float):
            id = int(identity)
            metaGroup = eos.db.getMetaGroup(id, *args, **kwargs)
        else:
            raise TypeError("Need MetaGroup object, integer, float or string as argument")
        return metaGroup

    def getMarketGroup(self, identity, *args, **kwargs):
        """Get market group by its ID"""
        if isinstance(identity, eos.types.MarketGroup):
            marketGroup = identity
        elif isinstance(identity, (int, float)):
            id = int(identity)
            marketGroup = eos.db.getMarketGroup(id, *args, **kwargs)
        else:
            raise TypeError("Need MarketGroup object, integer or float as argument")
        return marketGroup

    def getGroupByItem(self, item):
        """Get group by item"""
        if item.name in self.ITEMS_FORCEGROUP:
            group = self.ITEMS_FORCEGROUP[item.name]
        else:
            group = item.group
        return group

    def getCategoryByItem(self, item):
        """Get category by item"""
        grp = self.getGroupByItem(item)
        cat = grp.category
        return cat

    def getMetaGroupByItem(self, item):
        """Get meta group by item"""
        # Check if item is in forced metagroup map
        if item.name in self.ITEMS_FORCEDMETAGROUP:
            # Create meta group from scratch
            metaGroup = eos.types.MetaType()
            # Get meta group info object based on meta group name
            metaGroupInfo = self.getMetaGroup(self.ITEMS_FORCEDMETAGROUP[item.name][0])
            # Get parent item based on its name
            parent = self.getItem(self.ITEMS_FORCEDMETAGROUP[item.name][1])
            # Assign all required for metaGroup variables
            metaGroup.info = metaGroupInfo
            metaGroup.items = item
            metaGroup.parent = parent
            metaGroup.metaGroupID = metaGroupInfo.ID
            metaGroup.parentTypeID = parent.ID
            metaGroup.typeID = item.ID
        # If no forced meta group is provided, try to use item's
        # meta group if any
        else:
            metaGroup = item.metaGroup
        return metaGroup

    def getMetaGroupIdByItem(self, item, fallback=0):
        """Get meta group ID by item"""
        id = getattr(self.getMetaGroupByItem(item), "ID", fallback)
        return id

    def getMarketGroupByItem(self, item, parentcheck=True):
        """Get market group by item, its ID or name"""
        # Check if we force market group for given item
        if item.name in self.ITEMS_FORCEDMARKETGROUP:
            mgid = self.ITEMS_FORCEDMARKETGROUP[item.name]
            return self.getMarketGroup(mgid)
        # Check if item itself has market group
        elif item.marketGroupID:
            return item.marketGroup
        elif parentcheck:
            # If item doesn't have marketgroup, check if it has parent
            # item and use its market group
            parent = self.getParentItemByItem(item, selfparent=False)
            if parent:
                return parent.marketGroup
            else:
                return None
        else:
            return None

    def getParentItemByItem(self, item, selfparent=True):
        """Get parent item by item"""
        mg = self.getMetaGroupByItem(item)
        if mg:
            parent = mg.parent
        # Consider self as parent if item has no parent in database
        elif selfparent is True:
            parent = item
        else:
            parent = None
        return parent

    def getVariationsByItems(self, items, alreadyparent=False):
        """Get item variations by item, its ID or name"""
        # Set for IDs of parent items
        parents = set()
        # Set-container for variables
        variations = set()
        for item in items:
            # Get parent item
            if alreadyparent is False:
                parent = self.getParentItemByItem(item)
            else:
                parent = item
            # Combine both in the same set
            parents.add(parent)
            # Check for overrides and add them if any
            if parent.name in self.ITEMS_FORCEDMETAGROUP_R:
                for item in self.ITEMS_FORCEDMETAGROUP_R[parent.name]:
                    i = self.getItem(item)
                    if i:
                        variations.add(i)
        # Add all parents to variations set
        variations.update(parents)
        # Add all variations of parents to the set
        parentids = tuple(item.ID for item in parents)
        variations.update(eos.db.getVariations(parentids))
        return variations

    def getGroupsByCategory(self, cat):
        """Get groups from given category"""
        groups = set(filter(lambda grp: self.getPublicityByGroup(grp), cat.groups))
        return groups

    def getMarketGroupChildren(self, mg):
        """Get the children marketGroups of marketGroup."""
        children = set()
        for child in mg.children:
            children.add(child)
        return children

    def getItemsByGroup(self, group):
        """Get items assigned to group"""
        # Return only public items; also, filter out items
        # which were forcibly set to other groups
        groupItems = set(group.items)
        if hasattr(group, 'addItems'):
            groupItems.update(group.addItems)
        items = set(filter(lambda item: self.getPublicityByItem(item) and self.getGroupByItem(item) == group, groupItems))
        return items

    def getItemsByMarketGroup(self, mg, vars=True):
        """Get items in the given market group"""
        result = set()
        # Get items from eos market group
        baseitms = set(mg.items)
        # Add hardcoded items to set
        if mg.ID in self.ITEMS_FORCEDMARKETGROUP_R:
            forceditms = set(self.getItem(itmn) for itmn in self.ITEMS_FORCEDMARKETGROUP_R[mg.ID])
            baseitms.update(forceditms)
        if vars:
            parents = set()
            for item in baseitms:
                # Add one of the base market group items to result
                result.add(item)
                parent = self.getParentItemByItem(item, selfparent=False)
                # If item has no parent, it's base item (or at least should be)
                if parent is None:
                    parents.add(item)
            # Fetch variations only for parent items
            variations = self.getVariationsByItems(parents, alreadyparent=True)
            for variation in variations:
                # Exclude items with their own explicitly defined market groups
                if self.getMarketGroupByItem(variation, parentcheck=False) is None:
                    result.add(variation)
        else:
            result = baseitms
        # Get rid of unpublished items
        result = set(filter(lambda item: self.getPublicityByItem(item), result))
        return result

    def marketGroupHasTypesCheck(self, mg):
        """If market group has any items, return true"""
        if mg and mg.ID in self.ITEMS_FORCEDMARKETGROUP_R:
            return True
        elif len(mg.items) > 0:
            return True
        else:
            return False

    def marketGroupValidityCheck(self, mg):
        """Check market group validity"""
        # The only known case when group can be invalid is
        # when it's declared to have types, but it doesn't contain anything
        if mg.ID in self.FORCEDMARKETGROUP:
            return self.FORCEDMARKETGROUP[mg.ID]
        if mg.hasTypes and not self.marketGroupHasTypesCheck(mg):
            return False
        else:
            return True

    def getIconByMarketGroup(self, mg):
        """Return icon associated to marketgroup"""
        if mg.icon:
            return mg.icon.iconFile
        else:
            while mg and not mg.hasTypes:
                mg = mg.parent
            if not mg:
                return ""
            elif self.marketGroupHasTypesCheck(mg):
                # Do not request variations to make process faster
                # Pick random item and use its icon
                items = self.getItemsByMarketGroup(mg, vars=False)
                try:
                    item = items.pop()
                except KeyError:
                    return ""

                return item.icon.iconFile if item.icon else ""
            elif self.getMarketGroupChildren(mg) > 0:
                kids = self.getMarketGroupChildren(mg)
                mktGroups = self.getIconByMarketGroup(kids)
                size = len(mktGroups)
                return mktGroups.pop() if size > 0 else ""
            else:
                return ""

    def getPublicityByItem(self, item):
        """Return if an item is published"""
        if item.name in self.ITEMS_FORCEPUBLISHED:
            pub = self.ITEMS_FORCEPUBLISHED[item.name]
        else:
            pub = item.published
        return pub

    def getPublicityByGroup(self, group):
        """Return if an group is published"""
        if group.name in self.GROUPS_FORCEPUBLISHED:
            pub = self.GROUPS_FORCEPUBLISHED[group.name]
        else:
            pub = group.published
        return pub

    def getMarketRoot(self):
        """
        Get the root of the market tree.
        Returns a list, where each element is a tuple containing:
        the ID, the name and the icon of the group
        """
        root = set()
        for id in self.ROOT_MARKET_GROUPS:
            mg = self.getMarketGroup(id, eager="icon")
            root.add(mg)

        return root

    def getShipRoot(self):
        cat1 = self.getCategory("舰船")
        cat2 = self.getCategory("建筑")
        root = set(self.getGroupsByCategory(cat1) | self.getGroupsByCategory(cat2))

        return root

    def getShipList(self, grpid):
        """Get ships for given group id"""
        grp = self.getGroup(grpid, eager=("items", "items.group", "items.marketGroup"))
        ships = self.getItemsByGroup(grp)
        for ship in ships:
            ship.race
        return ships

    def getShipListDelayed(self, id, callback):
        """Background version of getShipList"""
        self.shipBrowserWorkerThread.queue.put((id, callback))

    def searchShips(self, name):
        """Find ships according to given text pattern"""
        filter = eos.types.Category.name.in_(["舰船", "建筑"])
        results = eos.db.searchItems(name, where=filter,
                                     join=(eos.types.Item.group, eos.types.Group.category),
                                     eager=("icon", "group.category", "metaGroup", "metaGroup.parent"))
        ships = set()
        for item in results:
            if self.getPublicityByItem(item):
                ships.add(item)
        return ships

    def searchItems(self, name, callback, filterOn=True):
        """Find items according to given text pattern"""
        self.searchWorkerThread.scheduleSearch(name, callback, filterOn)

    def getItemsWithOverrides(self):
        overrides = eos.db.getAllOverrides()
        items = set()
        for x in overrides:
            if (x.item is None):
                eos.db.saveddata_session.delete(x)
                eos.db.commit()
            else:
                items.add(x.item)
        return list(items)

    def directAttrRequest(self, items, attribs):
        try:
            itemIDs = tuple(map(lambda i: i.ID, items))
        except TypeError:
            itemIDs = (items.ID,)
        try:
            attrIDs = tuple(map(lambda i: i.ID, attribs))
        except TypeError:
            attrIDs = (attribs.ID,)
        info = {}
        for itemID, typeID, val in eos.db.directAttributeRequest(itemIDs, attrIDs):
            info[itemID] = val

        return info

    def getImplantTree(self):
        """Return implant market group children"""
        img = self.getMarketGroup(27)
        return self.getMarketGroupChildren(img)

    def filterItemsByMeta(self, items, metas):
        """Filter items by meta lvl"""
        filtered = set(filter(lambda item: self.getMetaGroupIdByItem(item) in metas, items))
        return filtered

    def getPriceNow(self, typeID):
        """Get price for provided typeID"""
        price = self.priceCache.get(typeID)
        if price is None:
            price = eos.db.getPrice(typeID)
            if price is None:
                price = eos.types.Price(typeID)
                eos.db.add(price)

            self.priceCache[typeID] = price

        return price

    def getPricesNow(self, typeIDs):
        """Return map of calls to get price against list of typeIDs"""
        return map(self.getPrice, typeIDs)

    def getPrices(self, typeIDs, callback):
        """Get prices for multiple typeIDs"""
        requests = []
        for typeID in typeIDs:
            price = self.getPriceNow(typeID)
            requests.append(price)

        def cb():
            try:
                callback(requests)
            except Exception, e:
                pass
            eos.db.commit()

        self.priceWorkerThread.trigger(requests, cb)

    def waitForPrice(self, item, callback):
        """
        Wait for prices to be fetched and callback when finished. This is used with the column prices for modules.
        Instead of calling them individually, we set them to wait until the entire fit price is called and calculated
        (see GH #290)
        """

        def cb():
            try:
                callback(item)
            except:
                pass

        self.priceWorkerThread.setToWait(item.ID, cb)

    def clearPriceCache(self):
        self.priceCache.clear()
        deleted_rows = eos.db.clearPrices()

    def getSystemWideEffects(self):
        """
        Get dictionary with system-wide effects
        """
        # Container for system-wide effects
        effects = {}
        # Expressions for matching when detecting effects we're looking for
        validgroups = ("Black Hole Effect Beacon",
                       "Cataclysmic Variable Effect Beacon",
                       "Magnetar Effect Beacon",
                       "Pulsar Effect Beacon",
                       "Red Giant Beacon",
                       "Wolf Rayet Effect Beacon",
                       "Incursion ship attributes effects")
        # Stuff we don't want to see in names
        garbages = ("Effect", "Beacon", "ship attributes effects")
        # Get group with all the system-wide beacons
        grp = self.getGroup("Effect Beacon")
        beacons = self.getItemsByGroup(grp)
        # Cycle through them
        for beacon in beacons:
            # Check if it belongs to any valid group
            for group in validgroups:
                # Check beginning of the name only
                if re.match(group, beacon.name):
                    # Get full beacon name
                    beaconname = beacon.name
                    for garbage in garbages:
                        beaconname = re.sub(garbage, "", beaconname)
                    beaconname = re.sub(" {2,}", " ", beaconname).strip()
                    # Get short name
                    shortname = re.sub(group, "", beacon.name)
                    for garbage in garbages:
                        shortname = re.sub(garbage, "", shortname)
                    shortname = re.sub(" {2,}", " ", shortname).strip()
                    # Get group name
                    groupname = group
                    for garbage in garbages:
                        groupname = re.sub(garbage, "", groupname)
                    groupname = re.sub(" {2,}", " ", groupname).strip()
                    # Add stuff to dictionary
                    if not groupname in effects:
                        effects[groupname] = set()
                    effects[groupname].add((beacon, beaconname, shortname))
                    # Break loop on 1st result
                    break
        return effects
