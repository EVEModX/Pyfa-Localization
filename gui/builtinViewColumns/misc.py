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

from gui import builtinViewColumns
from gui.viewColumn import ViewColumn
from gui import bitmapLoader
from gui.utils.numberFormatter import formatAmount

import wx

class Miscellanea(ViewColumn):
    name = "Miscellanea"
    def __init__(self, fittingView, params = None):
        if params == None:
            params = {"showIcon": True,
                      "displayName": False}
        ViewColumn.__init__(self, fittingView)
        if params["showIcon"]:
            self.imageId = fittingView.imageList.GetImageIndex("column_misc", "icons")
            self.bitmap = bitmapLoader.getBitmap("column_misc", "icons")
            self.mask = wx.LIST_MASK_IMAGE
        else:
            self.imageId = -1

        if params["displayName"] or self.imageId == -1:
            self.columnText = "Misc data"
            self.mask |= wx.LIST_MASK_TEXT

    def getText(self, stuff):
        text = self.__getData(stuff)[0]
        return text

    def getToolTip(self, mod):
        import random
        return "Tracking {}".format(random.random())

    def getImageId(self, mod):
        return -1

    def getParameters(self):
        return (("displayName", bool, False),
                ("showIcon", bool, True))


    def __getData(self, stuff):
        item = stuff.item
        if item is None:
            return "", None
        itemGroup = item.group.name
        if itemGroup in ("Energy Weapon", "Hybrid Weapon", "Projectile Weapon", "Combat Drone", "Fighter Drone"):
            trackingSpeed = stuff.getModifiedItemAttr("trackingSpeed")
            if not trackingSpeed:
                return "", None
            return "{0}".format(formatAmount(trackingSpeed, 3, 0, 3)), None
        elif itemGroup == "Energy Destabilizer":
            neutAmount = stuff.getModifiedItemAttr("energyDestabilizationAmount")
            cycleTime = stuff.cycleTime
            if not neutAmount or not cycleTime:
                return "", None
            capPerSec = float(-neutAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(capPerSec, 3, 0, 3)), None
        elif itemGroup == "Energy Vampire":
            neutAmount = stuff.getModifiedItemAttr("powerTransferAmount")
            cycleTime = stuff.cycleTime
            if not neutAmount or not cycleTime:
                return "", None
            capPerSec = float(-neutAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(capPerSec, 3, 0, 3)), None
        elif itemGroup in ("Salvager", "Data Miners"):
            chance = stuff.getModifiedItemAttr("accessDifficultyBonus")
            if not chance:
                return "", None
            return "{0}%".format(formatAmount(chance, 3, 0, 3)), None
        elif itemGroup in ("Warp Scrambler", "Warp Core Stabilizer"):
            scramStr = stuff.getModifiedItemAttr("warpScrambleStrength")
            if not scramStr:
                return "", None
            return "{0}".format(formatAmount(-scramStr, 3, 0, 3, forceSign=True)), None
        elif itemGroup in ("Stasis Web", "Stasis Webifying Drone"):
            speedFactor = stuff.getModifiedItemAttr("speedFactor")
            if not speedFactor:
                return "", None
            return "{0}%".format(formatAmount(speedFactor, 3, 0, 3)), None
        elif itemGroup in ("Stasis Web", "Stasis Webifying Drone"):
            speedFactor = stuff.getModifiedItemAttr("speedFactor")
            if not speedFactor:
                return "", None
            return "{0}%".format(formatAmount(speedFactor, 3, 0, 3)), None
        elif itemGroup == "Target Painter":
            sigRadBonus = stuff.getModifiedItemAttr("signatureRadiusBonus")
            if not sigRadBonus:
                return "", None
            return "{0}%".format(formatAmount(sigRadBonus, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Remote Sensor Damper":
            lockRangeBonus = stuff.getModifiedItemAttr("maxTargetRangeBonus")
            scanResBonus = stuff.getModifiedItemAttr("scanResolutionBonus")
            if lockRangeBonus is None or scanResBonus is None:
                return "", None
            display = 0
            for bonus in (lockRangeBonus, scanResBonus):
                if abs(bonus) > abs(display):
                    display = bonus
            if not display:
                return "", None
            return "{0}%".format(formatAmount(display, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Tracking Disruptor":
            optimalRangeBonus = stuff.getModifiedItemAttr("maxRangeBonus")
            falloffRangeBonus = stuff.getModifiedItemAttr("falloffBonus")
            trackingSpeedBonus = stuff.getModifiedItemAttr("trackingSpeedBonus")
            if optimalRangeBonus is None or falloffRangeBonus is None or trackingSpeedBonus is None:
                return "", None
            display = 0
            for bonus in (optimalRangeBonus, falloffRangeBonus, trackingSpeedBonus):
                if abs(bonus) > abs(display):
                    display = bonus
            if not display:
                return "", None
            return "{0}%".format(formatAmount(display, 3, 0, 3, forceSign=True)), None
        elif itemGroup in ("ECM", "ECM Burst", "Remote ECM Burst"):
            grav = stuff.getModifiedItemAttr("scanGravimetricStrengthBonus")
            ladar = stuff.getModifiedItemAttr("scanLadarStrengthBonus")
            radar = stuff.getModifiedItemAttr("scanRadarStrengthBonus")
            magnet = stuff.getModifiedItemAttr("scanMagnetometricStrengthBonus")
            if grav is None or ladar is None or radar is None or magnet is None:
                return "", None
            display = max(grav, ladar, radar, magnet)
            if not display:
                return "", None
            return "{0}".format(formatAmount(display, 3, 0, 3)), None
        elif itemGroup == "Remote Sensor Booster":
            scanResBonus = stuff.getModifiedItemAttr("scanResolutionBonus")
            lockRangeBonus = stuff.getModifiedItemAttr("maxTargetRangeBonus")
            if scanResBonus is None or lockRangeBonus is None:
                return "", None
            display = 0
            for bonus in (scanResBonus, lockRangeBonus):
                if abs(bonus) > abs(display):
                    display = bonus
            if not display:
                return "", None
            return "{0}%".format(formatAmount(display, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Projected ECCM":
            grav = stuff.getModifiedItemAttr("scanGravimetricStrengthPercent")
            ladar = stuff.getModifiedItemAttr("scanLadarStrengthPercent")
            radar = stuff.getModifiedItemAttr("scanRadarStrengthPercent")
            magnet = stuff.getModifiedItemAttr("scanMagnetometricStrengthPercent")
            if grav is None or ladar is None or radar is None or magnet is None:
                return "", None
            display = max(grav, ladar, radar, magnet)
            if not display:
                return "", None
            return "{0}%".format(formatAmount(display, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Cloaking Device":
            recalibration = stuff.getModifiedItemAttr("cloakingTargetingDelay")
            if recalibration is None:
                return "", None
            return "{0}s".format(formatAmount(float(recalibration)/1000, 3, 0, 3)), None
        elif itemGroup == "Armor Repair Projector":
            repAmount = stuff.getModifiedItemAttr("armorDamageAmount")
            cycleTime = stuff.getModifiedItemAttr("duration")
            if not repAmount or not cycleTime:
                return "", None
            repPerSec = float(repAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(repPerSec, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Shield Transporter":
            repAmount = stuff.getModifiedItemAttr("shieldBonus")
            cycleTime = stuff.cycleTime
            if not repAmount or not cycleTime:
                return "", None
            repPerSec = float(repAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(repPerSec, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Energy Transfer Array":
            repAmount = stuff.getModifiedItemAttr("powerTransferAmount")
            cycleTime = stuff.cycleTime
            if not repAmount or not cycleTime:
                return "", None
            repPerSec = float(repAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(repPerSec, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Gang Coordinator":
            command = stuff.getModifiedItemAttr("commandBonus")
            if not command:
                return "", None
            return "{0}%".format(formatAmount(command, 3, 0, 3, forceSign=True)), None
        elif itemGroup == "Electronic Warfare Drone":
            sigRadBonus = stuff.getModifiedItemAttr("signatureRadiusBonus")
            lockRangeMult = stuff.getModifiedItemAttr("maxTargetRangeMultiplier")
            scanResMult = stuff.getModifiedItemAttr("scanResolutionMultiplier")
            falloffRangeMult = stuff.getModifiedItemAttr("fallofMultiplier")
            optimalRangeMult = stuff.getModifiedItemAttr("maxRangeMultiplier")
            trackingSpeedMult = stuff.getModifiedItemAttr("trackingSpeedMultiplier")
            grav = stuff.getModifiedItemAttr("scanGravimetricStrengthBonus")
            ladar = stuff.getModifiedItemAttr("scanLadarStrengthBonus")
            radar = stuff.getModifiedItemAttr("scanRadarStrengthBonus")
            magnet = stuff.getModifiedItemAttr("scanMagnetometricStrengthBonus")
            if sigRadBonus:
                return "{0}%".format(formatAmount(sigRadBonus, 3, 0, 3, forceSign=True)), None
            if lockRangeMult is not None and scanResMult is not None:
                display = 0
                for bonus in ((lockRangeMult-1)*100, (scanResMult-1)*100):
                    if abs(bonus) > abs(display):
                        display = bonus
                if not display:
                    return "", None
                return "{0}%".format(formatAmount(display, 3, 0, 3, forceSign=True)), None
            if falloffRangeMult is not None and optimalRangeMult is not None and trackingSpeedMult is not None:
                display = 0
                for bonus in ((falloffRangeMult-1)*100, (optimalRangeMult-1)*100, (trackingSpeedMult-1)*100):
                    if abs(bonus) > abs(display):
                        display = bonus
                if not display:
                    return "", None
                return "{0}%".format(formatAmount(display, 3, 0, 3), forceSign=True), None
            if grav is not None and ladar is not None and radar is not None and magnet is not None:
                display = max(grav, ladar, radar, magnet)
                if not display:
                    return "", None
                return "{0}".format(formatAmount(display, 3, 0, 3)), None
            else:
                return "", None
        elif itemGroup == "Fighter Bomber":
            optimalSig = stuff.getModifiedItemAttr("optimalSigRadius")
            if not optimalSig:
                return "", None
            return "{0}m".format(formatAmount(optimalSig, 3, 0, 3)), None
        elif itemGroup == "Logistic Drone":
            repAmount = stuff.getModifiedItemAttr("armorDamageAmount") or stuff.getModifiedItemAttr("shieldBonus")
            cycleTime = stuff.getModifiedItemAttr("duration")
            if not repAmount or not cycleTime:
                return "", None
            repPerSec = float(repAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(repPerSec, 3, 0, 3)), None
        elif itemGroup == "Cap Drain Drone":
            neutAmount = stuff.getModifiedItemAttr("energyDestabilizationAmount")
            cycleTime = stuff.getModifiedItemAttr("duration")
            if not neutAmount or not cycleTime:
                return "", None
            capPerSec = float(-neutAmount) * 1000 / cycleTime
            return "{0}/s".format(formatAmount(capPerSec, 3, 0, 3)), None
        elif stuff.charge is not None:
            chargeGroup = stuff.charge.group.name
            if chargeGroup in ("Rocket", "Advanced Rocket", "Light Missile", "Advanced Light Missile", "FoF Light Missile",
                               "Assault Missile", "Advanced Assault Missile", "Heavy Missile", "Advanced Heavy Missile", "FoF Heavy Missile",
                               "Torpedo", "Advanced Torpedo", "Cruise Missile", "Advanced Cruise Missile", "FoF Cruise Missile",
                               "Citadel Torpedo", "Citadel Cruise"):
                cloudSize = stuff.getModifiedChargeAttr("aoeCloudSize")
                aoeVelocity = stuff.getModifiedChargeAttr("aoeVelocity")
                if not cloudSize or not aoeVelocity:
                    return "", None
                return "{0}{1} | {2}{3}".format(formatAmount(cloudSize, 3, 0, 3), "m",
                                                formatAmount(aoeVelocity, 3, 0, 3), "m/s"), None
            elif chargeGroup == "Bomb":
                cloudSize = stuff.getModifiedChargeAttr("aoeCloudSize")
                if not cloudSize:
                    return "", None
                return "{0}{1}".format(formatAmount(cloudSize, 3, 0, 3), "m"), None
            elif chargeGroup in ("Scanner Probe",):
                scanStr = stuff.getModifiedChargeAttr("baseSensorStrength")
                if not scanStr:
                    return "", None
                return "{0}".format(formatAmount(scanStr, 3, 0, 3)), None
            else:
                return "", None
        else:
            return "", None

Miscellanea.register()