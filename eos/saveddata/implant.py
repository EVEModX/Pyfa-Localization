#===============================================================================
# Copyright (C) 2010 Diego Duclos
#
# This file is part of eos.
#
# eos is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# eos is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with eos.  If not, see <http://www.gnu.org/licenses/>.
#===============================================================================

from eos.modifiedAttributeDict import ModifiedAttributeDict, ItemAttrShortcut
from eos.effectHandlerHelpers import HandledItem
from sqlalchemy.orm import validates, reconstructor
import eos.db
import logging

logger = logging.getLogger(__name__)

class Implant(HandledItem, ItemAttrShortcut):
    def __init__(self, item):
        self.__item = item

        if self.isInvalid:
            raise ValueError("Passed item is not an Implant")

        self.itemID = item.ID if item is not None else None
        self.active = True
        self.build()

    @reconstructor
    def init(self):
        self.__item = None

        if self.itemID:
            self.__item = eos.db.getItem(self.itemID)
            if self.__item is None:
                logger.error("Item (id: %d) does not exist", self.itemID)
                return

        if self.isInvalid:
            logger.error("Item (id: %d) is not an Implant", self.itemID)
            return

        self.build()

    def build(self):
        """ Build object. Assumes proper and valid item already set """
        self.__itemModifiedAttributes = ModifiedAttributeDict()
        self.__itemModifiedAttributes.original = self.__item.attributes
        self.__itemModifiedAttributes.overrides = self.__item.overrides
        self.__slot = self.__calculateSlot(self.__item)

    @property
    def itemModifiedAttributes(self):
        return self.__itemModifiedAttributes

    @property
    def isInvalid(self):
        return self.__item is None or self.__item.category.name != "Implant"

    @property
    def slot(self):
        return self.__slot

    @property
    def item(self):
        return self.__item

    def __calculateSlot(self, item):
        if not "implantness" in item.attributes:
            raise ValueError("Passed item is not an implant")

        return int(item.attributes["implantness"].value)

    def clear(self):
        self.itemModifiedAttributes.clear()

    def calculateModifiedAttributes(self, fit, runTime, forceProjected = False):
        if forceProjected: return
        if self.active == False: return
        for effect in self.item.effects.itervalues():
            if effect.runTime == runTime and effect.isType("passive"):
                effect.handler(fit, self, ("implant",))

    @validates("fitID", "itemID", "active")
    def validator(self, key, val):
        map = {"fitID": lambda val: isinstance(val, int),
               "itemID" : lambda val: isinstance(val, int),
               "active": lambda val: isinstance(val, bool)}

        if map[key](val) == False: raise ValueError(str(val) + " is not a valid value for " + key)
        else: return val

    def __deepcopy__(self, memo):
        copy = Implant(self.item)
        copy.active = self.active
        return copy

    def __repr__(self):
        return "Implant(ID={}, name={}) at {}".format(
            self.item.ID, self.item.name, hex(id(self))
        )
