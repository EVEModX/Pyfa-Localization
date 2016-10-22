# eliteBonusLogiFrigArmorHP2
#
# Used by:
# Ship: Deacon
#coding: UTF-8
type = "passive"
def handler(fit, src, context):
    fit.ship.boostItemAttr("armorHP", src.getModifiedItemAttr("eliteBonusLogiFrig2"), skill=u"运输舰")
