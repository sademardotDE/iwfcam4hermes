"""Auto-generated JNI stubs for iWFCam (libZGP2PComm.so)."""

JNI_FUNCTIONS = [
    "ASFGetPlayFileResultion",
    "ASFGetPlayFileTimeLong",
    "ASFGetPlayFileVRCamType",
    "ASFGetPlaySpeed",
    "ASFGotoTimeV",
    "ASFPausePlay",
    "ASFPlayFile",
    "ASFSetPlaySpeed",
    "ASFStopPlay",
    "ASFisPlaying",
    "ASFisRuning",
    "AddNewP2PDevice",
    "DEVDestory",
    "DEVGetDevLastError",
    "DEVGetDevStatus",
    "DEVGetOnlineUserCnt",
    "DEVInitP2PDeviceServer",
    "DEVSendAudioFrameData",
    "DEVSendVideoFrameData",
    "DEVSetAVParams",
    "DEVSetMyLocalIP",
    "DeleteP2PDevice",
    "DestoryP2PComm",
    "DevAPWifiInforDoRead",
    "DevAPWifiInforScan",
    "DevCallCode",
    "DevShareCode",
    "ELAINGetLibVersion",
    "ELAINGetProtoVersion",
    "ELAINInitSmartConnection",
    "ELAINStartSmartConnection",
    "ELAINStopSmartConnection",
    "GetWIFIConfigStatus",
    "InitP2PServer",
    "P2PAECProcPlayAudio",
    "P2PAECProcess",
    "P2PCloudChkCurrRecfileInfor",
    "P2PCloudGetDownloadRemainSec",
    "P2PCloudHaveThisGMTTimeRec",
    "P2PCloudIsSupport",
    "P2PCloudPausePlay",
    "P2PCloudPlayThisGMTTimeRec",
    "P2PCloudReadDeviceCfg",
    "P2PCloudReadKeyInfor",
    "P2PCloudReadSevInfor",
    "P2PCloudReadSevInforX",
    "P2PCloudRegKey",
    "P2PCloudRequDeviceCfg",
    "P2PCloudSetDeviceCfg",
    "P2PCloudSetPlayCacheDir",
    "P2PCloudStartDownloadCloudSave",
    "P2PCloudStopDownload",
    "P2PCloudStopPlay",
    "P2PDevCGIProc",
    "P2PDevISSupportCGI",
    "P2PDevSnapshotFrameDec",
    "P2PDevUploadFileDelete",
    "P2PDevUploadFilePlay",
    "P2PDevUploadFileSetTime",
    "P2PDevUploadStart",
    "P2PUIDGetUIDID",
    "PetFeedDoFeed",
    "PetFeedReadRec",
    "PetFeedReadSch",
    "PetFeedReadStatus",
    "PetFeedRefreshAllRec",
    "PetFeedRefreshSCH",
    "PetFeedRefreshStatus",
    "PetFeedSaveCurrFeedSch",
    "PetFeedSetSch",
    "PetFeedSyncTime",
    "PetFeedWeightRemark",
    "ResetNetworkCnnt",
    "SetMAppPushInfor",
    "StartSehP2PDeviceStatus",
    "StartWIFIConfig",
    "StopP2PDeviceAVMedia",
    "StopWIFIConfig",
    "UPKCheckUpdate",
    "UPKDoUpgrade",
    "UPKGetPackInfor",
    "UPKGetStatus",
    "UpdateP2PDevice",
    "VRNDBindCamYUVTextureRender",
    "VRNDGetCameraType",
    "VRNDGetLenShowMode",
    "VRNDGetLenShowStatus",
    "VRNDGetRenderMode",
    "VRNDResetVideo",
    "VRNDSetupCameraType",
    "VRNDSwitchVRMode",
    "VRNDUpdateExtTextureShow",
    "VRNDUpdateImageTextureShow",
    "VRNDgetScaleFactor",
    "VRNDisVRCam",
    "VRNDonDoubleTap",
    "VRNDonDrawFrame",
    "VRNDonLongPress",
    "VRNDonScroll",
    "VRNDonSingleTapUp",
    "VRNDonSurfaceChanged",
    "VRNDonSurfaceCreated",
    "VRNDsetDispOffset",
    "VRNDsetScaleFactor",
    "VRNDsetScaleValue",
    "VRNDsetVideoScaleMode",
    "addDownloadFile",
    "addP2PDevSchTimerItem",
    "addP2PDevSchTimerItemType",
    "clearP2PDevSchTimerItem",
    "clearP2PDevSchTimerItemType",
    "closeDeviceConnection",
    "delDevSDCardFile",
    "delDownloadFile",
    "delP2PDevSchTimerItem",
    "delP2PDevSchTimerItemType",
    "doDevReboot",
    "doP2PDev433MOper",
    "endP2PDevSchTimerItem",
    "endP2PDevSchTimerItemType",
    "getDevP2PVersion",
    "getDevSDCardRecFileThumb",
    "getDevSDCardRecFileThumbStatus",
    "getDevSchRecvType",
    "getP2PDevAccoInfor",
    "getP2PDevMsgReadStatus",
    "getP2PDeviceCurrLiveMode",
    "getP2PDeviceLastError",
    "getP2PDeviceLinkMode",
    "getP2PDeviceOnlineUserCnt",
    "getP2PDeviceStatus",
    "getRecordStatus",
    "getVersion",
    "haveDevManagePwd",
    "isDevSDCardPlayerFree",
    "isP2PDevAlarmOpened",
    "isP2PDevInAPMode",
    "keepP2PDeviceWakeup",
    "pauseDevSDCardPlay",
    "playDevMusic",
    "playDevSDCardRecFile",
    "playDevSDCardRecFileGoto",
    "reConnectDevice",
    "readCKDoorCfg",
    "readCKFHQCfgDef",
    "readCKFHQInfor",
    "readDevSleepModeCfg",
    "readP2PDev433MInfor",
    "readP2PDev433MSensor",
    "readP2PDev4GInfor",
    "readP2PDevAPModeInfor",
    "readP2PDevAlarmConfigData",
    "readP2PDevAlarmValue",
    "readP2PDevDDNSConfigData",
    "readP2PDevEMailConfigData",
    "readP2PDevEMailTestResData",
    "readP2PDevFTPConfigData",
    "readP2PDevFTPTestResData",
    "readP2PDevIPInfor",
    "readP2PDevIRLedConfigData",
    "readP2PDevMuiscFile",
    "readP2PDevMuiscInfor",
    "readP2PDevNTPConfigData",
    "readP2PDevRecFileData",
    "readP2PDevRecFileItem",
    "readP2PDevRecPlayMediaInfor",
    "readP2PDevSDCardRecCfg",
    "readP2PDevSchClockActive",
    "readP2PDevSchInfor",
    "readP2PDevSchInforType",
    "readP2PDevSchItem",
    "readP2PDevSchItemType",
    "readP2PDevUploadFileInfor",
    "readP2PDevUploadFileItem",
    "readP2PDevUploadStatus",
    "readP2PDevUserData",
    "readP2PDevUserItem",
    "readP2PDevUserItemCount",
    "readP2PDevWifiApItem",
    "readP2PDevWifiInforData",
    "readP2PDeviceMediaParams",
    "recordP2PDeviceStart",
    "recordP2PDeviceStartWithType",
    "recordP2PDeviceStop",
    "reqDev4GInfor",
    "reqDevAPModeInfor",
    "reqDevAlarmConfig",
    "reqDevDDNSConfig",
    "reqDevEMailConfig",
    "reqDevEMailTestRes",
    "reqDevFTPConfig",
    "reqDevFTPTestRes",
    "reqDevIPInfor",
    "reqDevIRLedConfig",
    "reqDevMusic",
    "reqDevNTPConfig",
    "reqDevSchInfor",
    "reqDevSchInforType",
    "reqDevSleepModeCfg",
    "reqDevUploadFileInfor",
    "reqDevUserInfor",
    "reqDevWifiInfor",
    "reqP2PDev433MInfor",
    "reqP2PDevSDCardRecConfig",
    "reqP2PDeviceAVMedia",
    "reqP2PDeviceRelayData",
    "reqP2PDeviceTalk",
    "reqP2PSDCardAllFiles",
    "requCKDoorCfg",
    "requCKFHQCfg",
    "requP2PDevSchClockActive",
    "requP2PDeviceSnapshotImg",
    "resetDevSchInfor",
    "resetP2PDevAlarm",
    "resetP2PDevSchClockActive",
    "resetP2PDevUserInfor",
    "resetP2PDeviceLastError",
    "saveDevSchInfor",
    "saveDevSchInforType",
    "saveP2PDevSnapshot",
    "saveP2PDevUserInfor",
    "sendCKDoorCmd",
    "sendCKFHQCmd",
    "sendLanSehPackCmd",
    "sendP2PDeviceMediaCmd",
    "sendP2PDeviceTalkAudioData",
    "sendP2PDeviceUserData",
    "sendP2POtherData",
    "setCKDoorCfg",
    "setCKFHQCfg",
    "setDevAccessPwd",
    "setDevIRLedControl",
    "setDevIRLedOn",
    "setDevMusicPlayMode",
    "setDevNTPSyncTime",
    "setDevP2PLinkMode",
    "setDevSDCardPlaySpeed",
    "setDevSchItem",
    "setDevSchItemType",
    "setDevSleepModeCfg",
    "setH264DecoderMode",
    "setP2PDecoderWorkMode",
    "setP2PDevAPModeInfor",
    "setP2PDevAccessUserDisabled",
    "setP2PDevAlarmConfig",
    "setP2PDevAlarmOpen",
    "setP2PDevDDNSConfig",
    "setP2PDevEMailConfig",
    "setP2PDevFTPConfig",
    "setP2PDevIPInfor",
    "setP2PDevIRLedConfig",
    "setP2PDevLastMsgID",
    "setP2PDevNTPConfig",
    "setP2PDevName",
    "setP2PDevParam",
    "setP2PDevSDCardFormat",
    "setP2PDevSDCardRecCfg",
    "setP2PDevUserItem",
    "setP2PDevWifiConnect",
    "setP2PDevWifiDisconnect",
    "setP2PDevicePlayFps",
    "setP2PDeviceToSleep",
    "setP2PDeviceType",
    "setVideoCodecLock",
    "setVideoEncodeInfor",
    "setupP2PDevicePushMsg",
    "startP2PDevWifiScan",
    "stopDevMusicPlay",
    "stopDevSDCardRecFilePlay",
    "validDevManagePwd",
    "wakeUpP2PDevice",
]

class IWFCamJNI:
    """Stub class mirroring nvcP2PComm JNI surface."""
    pass

# Individual stubs
def ASFGetPlayFileResultion(*args, **kwargs):
    """Stub for ASFGetPlayFileResultion."""
    raise NotImplementedError('ARM library required')

def ASFGetPlayFileTimeLong(*args, **kwargs):
    """Stub for ASFGetPlayFileTimeLong."""
    raise NotImplementedError('ARM library required')

def ASFGetPlayFileVRCamType(*args, **kwargs):
    """Stub for ASFGetPlayFileVRCamType."""
    raise NotImplementedError('ARM library required')

def ASFGetPlaySpeed(*args, **kwargs):
    """Stub for ASFGetPlaySpeed."""
    raise NotImplementedError('ARM library required')

def ASFGotoTimeV(*args, **kwargs):
    """Stub for ASFGotoTimeV."""
    raise NotImplementedError('ARM library required')

def ASFPausePlay(*args, **kwargs):
    """Stub for ASFPausePlay."""
    raise NotImplementedError('ARM library required')

def ASFPlayFile(*args, **kwargs):
    """Stub for ASFPlayFile."""
    raise NotImplementedError('ARM library required')

def ASFSetPlaySpeed(*args, **kwargs):
    """Stub for ASFSetPlaySpeed."""
    raise NotImplementedError('ARM library required')

def ASFStopPlay(*args, **kwargs):
    """Stub for ASFStopPlay."""
    raise NotImplementedError('ARM library required')

def ASFisPlaying(*args, **kwargs):
    """Stub for ASFisPlaying."""
    raise NotImplementedError('ARM library required')

def ASFisRuning(*args, **kwargs):
    """Stub for ASFisRuning."""
    raise NotImplementedError('ARM library required')

def AddNewP2PDevice(*args, **kwargs):
    """Stub for AddNewP2PDevice."""
    raise NotImplementedError('ARM library required')

def DEVDestory(*args, **kwargs):
    """Stub for DEVDestory."""
    raise NotImplementedError('ARM library required')

def DEVGetDevLastError(*args, **kwargs):
    """Stub for DEVGetDevLastError."""
    raise NotImplementedError('ARM library required')

def DEVGetDevStatus(*args, **kwargs):
    """Stub for DEVGetDevStatus."""
    raise NotImplementedError('ARM library required')

def DEVGetOnlineUserCnt(*args, **kwargs):
    """Stub for DEVGetOnlineUserCnt."""
    raise NotImplementedError('ARM library required')

def DEVInitP2PDeviceServer(*args, **kwargs):
    """Stub for DEVInitP2PDeviceServer."""
    raise NotImplementedError('ARM library required')

def DEVSendAudioFrameData(*args, **kwargs):
    """Stub for DEVSendAudioFrameData."""
    raise NotImplementedError('ARM library required')

def DEVSendVideoFrameData(*args, **kwargs):
    """Stub for DEVSendVideoFrameData."""
    raise NotImplementedError('ARM library required')

def DEVSetAVParams(*args, **kwargs):
    """Stub for DEVSetAVParams."""
    raise NotImplementedError('ARM library required')

def DEVSetMyLocalIP(*args, **kwargs):
    """Stub for DEVSetMyLocalIP."""
    raise NotImplementedError('ARM library required')

def DeleteP2PDevice(*args, **kwargs):
    """Stub for DeleteP2PDevice."""
    raise NotImplementedError('ARM library required')

def DestoryP2PComm(*args, **kwargs):
    """Stub for DestoryP2PComm."""
    raise NotImplementedError('ARM library required')

def DevAPWifiInforDoRead(*args, **kwargs):
    """Stub for DevAPWifiInforDoRead."""
    raise NotImplementedError('ARM library required')

def DevAPWifiInforScan(*args, **kwargs):
    """Stub for DevAPWifiInforScan."""
    raise NotImplementedError('ARM library required')

def DevCallCode(*args, **kwargs):
    """Stub for DevCallCode."""
    raise NotImplementedError('ARM library required')

def DevShareCode(*args, **kwargs):
    """Stub for DevShareCode."""
    raise NotImplementedError('ARM library required')

def ELAINGetLibVersion(*args, **kwargs):
    """Stub for ELAINGetLibVersion."""
    raise NotImplementedError('ARM library required')

def ELAINGetProtoVersion(*args, **kwargs):
    """Stub for ELAINGetProtoVersion."""
    raise NotImplementedError('ARM library required')

def ELAINInitSmartConnection(*args, **kwargs):
    """Stub for ELAINInitSmartConnection."""
    raise NotImplementedError('ARM library required')

def ELAINStartSmartConnection(*args, **kwargs):
    """Stub for ELAINStartSmartConnection."""
    raise NotImplementedError('ARM library required')

def ELAINStopSmartConnection(*args, **kwargs):
    """Stub for ELAINStopSmartConnection."""
    raise NotImplementedError('ARM library required')

def GetWIFIConfigStatus(*args, **kwargs):
    """Stub for GetWIFIConfigStatus."""
    raise NotImplementedError('ARM library required')

def InitP2PServer(*args, **kwargs):
    """Stub for InitP2PServer."""
    raise NotImplementedError('ARM library required')

def P2PAECProcPlayAudio(*args, **kwargs):
    """Stub for P2PAECProcPlayAudio."""
    raise NotImplementedError('ARM library required')

def P2PAECProcess(*args, **kwargs):
    """Stub for P2PAECProcess."""
    raise NotImplementedError('ARM library required')

def P2PCloudChkCurrRecfileInfor(*args, **kwargs):
    """Stub for P2PCloudChkCurrRecfileInfor."""
    raise NotImplementedError('ARM library required')

def P2PCloudGetDownloadRemainSec(*args, **kwargs):
    """Stub for P2PCloudGetDownloadRemainSec."""
    raise NotImplementedError('ARM library required')

def P2PCloudHaveThisGMTTimeRec(*args, **kwargs):
    """Stub for P2PCloudHaveThisGMTTimeRec."""
    raise NotImplementedError('ARM library required')

def P2PCloudIsSupport(*args, **kwargs):
    """Stub for P2PCloudIsSupport."""
    raise NotImplementedError('ARM library required')

def P2PCloudPausePlay(*args, **kwargs):
    """Stub for P2PCloudPausePlay."""
    raise NotImplementedError('ARM library required')

def P2PCloudPlayThisGMTTimeRec(*args, **kwargs):
    """Stub for P2PCloudPlayThisGMTTimeRec."""
    raise NotImplementedError('ARM library required')

def P2PCloudReadDeviceCfg(*args, **kwargs):
    """Stub for P2PCloudReadDeviceCfg."""
    raise NotImplementedError('ARM library required')

def P2PCloudReadKeyInfor(*args, **kwargs):
    """Stub for P2PCloudReadKeyInfor."""
    raise NotImplementedError('ARM library required')

def P2PCloudReadSevInfor(*args, **kwargs):
    """Stub for P2PCloudReadSevInfor."""
    raise NotImplementedError('ARM library required')

def P2PCloudReadSevInforX(*args, **kwargs):
    """Stub for P2PCloudReadSevInforX."""
    raise NotImplementedError('ARM library required')

def P2PCloudRegKey(*args, **kwargs):
    """Stub for P2PCloudRegKey."""
    raise NotImplementedError('ARM library required')

def P2PCloudRequDeviceCfg(*args, **kwargs):
    """Stub for P2PCloudRequDeviceCfg."""
    raise NotImplementedError('ARM library required')

def P2PCloudSetDeviceCfg(*args, **kwargs):
    """Stub for P2PCloudSetDeviceCfg."""
    raise NotImplementedError('ARM library required')

def P2PCloudSetPlayCacheDir(*args, **kwargs):
    """Stub for P2PCloudSetPlayCacheDir."""
    raise NotImplementedError('ARM library required')

def P2PCloudStartDownloadCloudSave(*args, **kwargs):
    """Stub for P2PCloudStartDownloadCloudSave."""
    raise NotImplementedError('ARM library required')

def P2PCloudStopDownload(*args, **kwargs):
    """Stub for P2PCloudStopDownload."""
    raise NotImplementedError('ARM library required')

def P2PCloudStopPlay(*args, **kwargs):
    """Stub for P2PCloudStopPlay."""
    raise NotImplementedError('ARM library required')

def P2PDevCGIProc(*args, **kwargs):
    """Stub for P2PDevCGIProc."""
    raise NotImplementedError('ARM library required')

def P2PDevISSupportCGI(*args, **kwargs):
    """Stub for P2PDevISSupportCGI."""
    raise NotImplementedError('ARM library required')

def P2PDevSnapshotFrameDec(*args, **kwargs):
    """Stub for P2PDevSnapshotFrameDec."""
    raise NotImplementedError('ARM library required')

def P2PDevUploadFileDelete(*args, **kwargs):
    """Stub for P2PDevUploadFileDelete."""
    raise NotImplementedError('ARM library required')

def P2PDevUploadFilePlay(*args, **kwargs):
    """Stub for P2PDevUploadFilePlay."""
    raise NotImplementedError('ARM library required')

def P2PDevUploadFileSetTime(*args, **kwargs):
    """Stub for P2PDevUploadFileSetTime."""
    raise NotImplementedError('ARM library required')

def P2PDevUploadStart(*args, **kwargs):
    """Stub for P2PDevUploadStart."""
    raise NotImplementedError('ARM library required')

def P2PUIDGetUIDID(*args, **kwargs):
    """Stub for P2PUIDGetUIDID."""
    raise NotImplementedError('ARM library required')

def PetFeedDoFeed(*args, **kwargs):
    """Stub for PetFeedDoFeed."""
    raise NotImplementedError('ARM library required')

def PetFeedReadRec(*args, **kwargs):
    """Stub for PetFeedReadRec."""
    raise NotImplementedError('ARM library required')

def PetFeedReadSch(*args, **kwargs):
    """Stub for PetFeedReadSch."""
    raise NotImplementedError('ARM library required')

def PetFeedReadStatus(*args, **kwargs):
    """Stub for PetFeedReadStatus."""
    raise NotImplementedError('ARM library required')

def PetFeedRefreshAllRec(*args, **kwargs):
    """Stub for PetFeedRefreshAllRec."""
    raise NotImplementedError('ARM library required')

def PetFeedRefreshSCH(*args, **kwargs):
    """Stub for PetFeedRefreshSCH."""
    raise NotImplementedError('ARM library required')

def PetFeedRefreshStatus(*args, **kwargs):
    """Stub for PetFeedRefreshStatus."""
    raise NotImplementedError('ARM library required')

def PetFeedSaveCurrFeedSch(*args, **kwargs):
    """Stub for PetFeedSaveCurrFeedSch."""
    raise NotImplementedError('ARM library required')

def PetFeedSetSch(*args, **kwargs):
    """Stub for PetFeedSetSch."""
    raise NotImplementedError('ARM library required')

def PetFeedSyncTime(*args, **kwargs):
    """Stub for PetFeedSyncTime."""
    raise NotImplementedError('ARM library required')

def PetFeedWeightRemark(*args, **kwargs):
    """Stub for PetFeedWeightRemark."""
    raise NotImplementedError('ARM library required')

def ResetNetworkCnnt(*args, **kwargs):
    """Stub for ResetNetworkCnnt."""
    raise NotImplementedError('ARM library required')

def SetMAppPushInfor(*args, **kwargs):
    """Stub for SetMAppPushInfor."""
    raise NotImplementedError('ARM library required')

def StartSehP2PDeviceStatus(*args, **kwargs):
    """Stub for StartSehP2PDeviceStatus."""
    raise NotImplementedError('ARM library required')

def StartWIFIConfig(*args, **kwargs):
    """Stub for StartWIFIConfig."""
    raise NotImplementedError('ARM library required')

def StopP2PDeviceAVMedia(*args, **kwargs):
    """Stub for StopP2PDeviceAVMedia."""
    raise NotImplementedError('ARM library required')

def StopWIFIConfig(*args, **kwargs):
    """Stub for StopWIFIConfig."""
    raise NotImplementedError('ARM library required')

def UPKCheckUpdate(*args, **kwargs):
    """Stub for UPKCheckUpdate."""
    raise NotImplementedError('ARM library required')

def UPKDoUpgrade(*args, **kwargs):
    """Stub for UPKDoUpgrade."""
    raise NotImplementedError('ARM library required')

def UPKGetPackInfor(*args, **kwargs):
    """Stub for UPKGetPackInfor."""
    raise NotImplementedError('ARM library required')

def UPKGetStatus(*args, **kwargs):
    """Stub for UPKGetStatus."""
    raise NotImplementedError('ARM library required')

def UpdateP2PDevice(*args, **kwargs):
    """Stub for UpdateP2PDevice."""
    raise NotImplementedError('ARM library required')

def VRNDBindCamYUVTextureRender(*args, **kwargs):
    """Stub for VRNDBindCamYUVTextureRender."""
    raise NotImplementedError('ARM library required')

def VRNDGetCameraType(*args, **kwargs):
    """Stub for VRNDGetCameraType."""
    raise NotImplementedError('ARM library required')

def VRNDGetLenShowMode(*args, **kwargs):
    """Stub for VRNDGetLenShowMode."""
    raise NotImplementedError('ARM library required')

def VRNDGetLenShowStatus(*args, **kwargs):
    """Stub for VRNDGetLenShowStatus."""
    raise NotImplementedError('ARM library required')

def VRNDGetRenderMode(*args, **kwargs):
    """Stub for VRNDGetRenderMode."""
    raise NotImplementedError('ARM library required')

def VRNDResetVideo(*args, **kwargs):
    """Stub for VRNDResetVideo."""
    raise NotImplementedError('ARM library required')

def VRNDSetupCameraType(*args, **kwargs):
    """Stub for VRNDSetupCameraType."""
    raise NotImplementedError('ARM library required')

def VRNDSwitchVRMode(*args, **kwargs):
    """Stub for VRNDSwitchVRMode."""
    raise NotImplementedError('ARM library required')

def VRNDUpdateExtTextureShow(*args, **kwargs):
    """Stub for VRNDUpdateExtTextureShow."""
    raise NotImplementedError('ARM library required')

def VRNDUpdateImageTextureShow(*args, **kwargs):
    """Stub for VRNDUpdateImageTextureShow."""
    raise NotImplementedError('ARM library required')

def VRNDgetScaleFactor(*args, **kwargs):
    """Stub for VRNDgetScaleFactor."""
    raise NotImplementedError('ARM library required')

def VRNDisVRCam(*args, **kwargs):
    """Stub for VRNDisVRCam."""
    raise NotImplementedError('ARM library required')

def VRNDonDoubleTap(*args, **kwargs):
    """Stub for VRNDonDoubleTap."""
    raise NotImplementedError('ARM library required')

def VRNDonDrawFrame(*args, **kwargs):
    """Stub for VRNDonDrawFrame."""
    raise NotImplementedError('ARM library required')

def VRNDonLongPress(*args, **kwargs):
    """Stub for VRNDonLongPress."""
    raise NotImplementedError('ARM library required')

def VRNDonScroll(*args, **kwargs):
    """Stub for VRNDonScroll."""
    raise NotImplementedError('ARM library required')

def VRNDonSingleTapUp(*args, **kwargs):
    """Stub for VRNDonSingleTapUp."""
    raise NotImplementedError('ARM library required')

def VRNDonSurfaceChanged(*args, **kwargs):
    """Stub for VRNDonSurfaceChanged."""
    raise NotImplementedError('ARM library required')

def VRNDonSurfaceCreated(*args, **kwargs):
    """Stub for VRNDonSurfaceCreated."""
    raise NotImplementedError('ARM library required')

def VRNDsetDispOffset(*args, **kwargs):
    """Stub for VRNDsetDispOffset."""
    raise NotImplementedError('ARM library required')

def VRNDsetScaleFactor(*args, **kwargs):
    """Stub for VRNDsetScaleFactor."""
    raise NotImplementedError('ARM library required')

def VRNDsetScaleValue(*args, **kwargs):
    """Stub for VRNDsetScaleValue."""
    raise NotImplementedError('ARM library required')

def VRNDsetVideoScaleMode(*args, **kwargs):
    """Stub for VRNDsetVideoScaleMode."""
    raise NotImplementedError('ARM library required')

def addDownloadFile(*args, **kwargs):
    """Stub for addDownloadFile."""
    raise NotImplementedError('ARM library required')

def addP2PDevSchTimerItem(*args, **kwargs):
    """Stub for addP2PDevSchTimerItem."""
    raise NotImplementedError('ARM library required')

def addP2PDevSchTimerItemType(*args, **kwargs):
    """Stub for addP2PDevSchTimerItemType."""
    raise NotImplementedError('ARM library required')

def clearP2PDevSchTimerItem(*args, **kwargs):
    """Stub for clearP2PDevSchTimerItem."""
    raise NotImplementedError('ARM library required')

def clearP2PDevSchTimerItemType(*args, **kwargs):
    """Stub for clearP2PDevSchTimerItemType."""
    raise NotImplementedError('ARM library required')

def closeDeviceConnection(*args, **kwargs):
    """Stub for closeDeviceConnection."""
    raise NotImplementedError('ARM library required')

def delDevSDCardFile(*args, **kwargs):
    """Stub for delDevSDCardFile."""
    raise NotImplementedError('ARM library required')

def delDownloadFile(*args, **kwargs):
    """Stub for delDownloadFile."""
    raise NotImplementedError('ARM library required')

def delP2PDevSchTimerItem(*args, **kwargs):
    """Stub for delP2PDevSchTimerItem."""
    raise NotImplementedError('ARM library required')

def delP2PDevSchTimerItemType(*args, **kwargs):
    """Stub for delP2PDevSchTimerItemType."""
    raise NotImplementedError('ARM library required')

def doDevReboot(*args, **kwargs):
    """Stub for doDevReboot."""
    raise NotImplementedError('ARM library required')

def doP2PDev433MOper(*args, **kwargs):
    """Stub for doP2PDev433MOper."""
    raise NotImplementedError('ARM library required')

def endP2PDevSchTimerItem(*args, **kwargs):
    """Stub for endP2PDevSchTimerItem."""
    raise NotImplementedError('ARM library required')

def endP2PDevSchTimerItemType(*args, **kwargs):
    """Stub for endP2PDevSchTimerItemType."""
    raise NotImplementedError('ARM library required')

def getDevP2PVersion(*args, **kwargs):
    """Stub for getDevP2PVersion."""
    raise NotImplementedError('ARM library required')

def getDevSDCardRecFileThumb(*args, **kwargs):
    """Stub for getDevSDCardRecFileThumb."""
    raise NotImplementedError('ARM library required')

def getDevSDCardRecFileThumbStatus(*args, **kwargs):
    """Stub for getDevSDCardRecFileThumbStatus."""
    raise NotImplementedError('ARM library required')

def getDevSchRecvType(*args, **kwargs):
    """Stub for getDevSchRecvType."""
    raise NotImplementedError('ARM library required')

def getP2PDevAccoInfor(*args, **kwargs):
    """Stub for getP2PDevAccoInfor."""
    raise NotImplementedError('ARM library required')

def getP2PDevMsgReadStatus(*args, **kwargs):
    """Stub for getP2PDevMsgReadStatus."""
    raise NotImplementedError('ARM library required')

def getP2PDeviceCurrLiveMode(*args, **kwargs):
    """Stub for getP2PDeviceCurrLiveMode."""
    raise NotImplementedError('ARM library required')

def getP2PDeviceLastError(*args, **kwargs):
    """Stub for getP2PDeviceLastError."""
    raise NotImplementedError('ARM library required')

def getP2PDeviceLinkMode(*args, **kwargs):
    """Stub for getP2PDeviceLinkMode."""
    raise NotImplementedError('ARM library required')

def getP2PDeviceOnlineUserCnt(*args, **kwargs):
    """Stub for getP2PDeviceOnlineUserCnt."""
    raise NotImplementedError('ARM library required')

def getP2PDeviceStatus(*args, **kwargs):
    """Stub for getP2PDeviceStatus."""
    raise NotImplementedError('ARM library required')

def getRecordStatus(*args, **kwargs):
    """Stub for getRecordStatus."""
    raise NotImplementedError('ARM library required')

def getVersion(*args, **kwargs):
    """Stub for getVersion."""
    raise NotImplementedError('ARM library required')

def haveDevManagePwd(*args, **kwargs):
    """Stub for haveDevManagePwd."""
    raise NotImplementedError('ARM library required')

def isDevSDCardPlayerFree(*args, **kwargs):
    """Stub for isDevSDCardPlayerFree."""
    raise NotImplementedError('ARM library required')

def isP2PDevAlarmOpened(*args, **kwargs):
    """Stub for isP2PDevAlarmOpened."""
    raise NotImplementedError('ARM library required')

def isP2PDevInAPMode(*args, **kwargs):
    """Stub for isP2PDevInAPMode."""
    raise NotImplementedError('ARM library required')

def keepP2PDeviceWakeup(*args, **kwargs):
    """Stub for keepP2PDeviceWakeup."""
    raise NotImplementedError('ARM library required')

def pauseDevSDCardPlay(*args, **kwargs):
    """Stub for pauseDevSDCardPlay."""
    raise NotImplementedError('ARM library required')

def playDevMusic(*args, **kwargs):
    """Stub for playDevMusic."""
    raise NotImplementedError('ARM library required')

def playDevSDCardRecFile(*args, **kwargs):
    """Stub for playDevSDCardRecFile."""
    raise NotImplementedError('ARM library required')

def playDevSDCardRecFileGoto(*args, **kwargs):
    """Stub for playDevSDCardRecFileGoto."""
    raise NotImplementedError('ARM library required')

def reConnectDevice(*args, **kwargs):
    """Stub for reConnectDevice."""
    raise NotImplementedError('ARM library required')

def readCKDoorCfg(*args, **kwargs):
    """Stub for readCKDoorCfg."""
    raise NotImplementedError('ARM library required')

def readCKFHQCfgDef(*args, **kwargs):
    """Stub for readCKFHQCfgDef."""
    raise NotImplementedError('ARM library required')

def readCKFHQInfor(*args, **kwargs):
    """Stub for readCKFHQInfor."""
    raise NotImplementedError('ARM library required')

def readDevSleepModeCfg(*args, **kwargs):
    """Stub for readDevSleepModeCfg."""
    raise NotImplementedError('ARM library required')

def readP2PDev433MInfor(*args, **kwargs):
    """Stub for readP2PDev433MInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDev433MSensor(*args, **kwargs):
    """Stub for readP2PDev433MSensor."""
    raise NotImplementedError('ARM library required')

def readP2PDev4GInfor(*args, **kwargs):
    """Stub for readP2PDev4GInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevAPModeInfor(*args, **kwargs):
    """Stub for readP2PDevAPModeInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevAlarmConfigData(*args, **kwargs):
    """Stub for readP2PDevAlarmConfigData."""
    raise NotImplementedError('ARM library required')

def readP2PDevAlarmValue(*args, **kwargs):
    """Stub for readP2PDevAlarmValue."""
    raise NotImplementedError('ARM library required')

def readP2PDevDDNSConfigData(*args, **kwargs):
    """Stub for readP2PDevDDNSConfigData."""
    raise NotImplementedError('ARM library required')

def readP2PDevEMailConfigData(*args, **kwargs):
    """Stub for readP2PDevEMailConfigData."""
    raise NotImplementedError('ARM library required')

def readP2PDevEMailTestResData(*args, **kwargs):
    """Stub for readP2PDevEMailTestResData."""
    raise NotImplementedError('ARM library required')

def readP2PDevFTPConfigData(*args, **kwargs):
    """Stub for readP2PDevFTPConfigData."""
    raise NotImplementedError('ARM library required')

def readP2PDevFTPTestResData(*args, **kwargs):
    """Stub for readP2PDevFTPTestResData."""
    raise NotImplementedError('ARM library required')

def readP2PDevIPInfor(*args, **kwargs):
    """Stub for readP2PDevIPInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevIRLedConfigData(*args, **kwargs):
    """Stub for readP2PDevIRLedConfigData."""
    raise NotImplementedError('ARM library required')

def readP2PDevMuiscFile(*args, **kwargs):
    """Stub for readP2PDevMuiscFile."""
    raise NotImplementedError('ARM library required')

def readP2PDevMuiscInfor(*args, **kwargs):
    """Stub for readP2PDevMuiscInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevNTPConfigData(*args, **kwargs):
    """Stub for readP2PDevNTPConfigData."""
    raise NotImplementedError('ARM library required')

def readP2PDevRecFileData(*args, **kwargs):
    """Stub for readP2PDevRecFileData."""
    raise NotImplementedError('ARM library required')

def readP2PDevRecFileItem(*args, **kwargs):
    """Stub for readP2PDevRecFileItem."""
    raise NotImplementedError('ARM library required')

def readP2PDevRecPlayMediaInfor(*args, **kwargs):
    """Stub for readP2PDevRecPlayMediaInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevSDCardRecCfg(*args, **kwargs):
    """Stub for readP2PDevSDCardRecCfg."""
    raise NotImplementedError('ARM library required')

def readP2PDevSchClockActive(*args, **kwargs):
    """Stub for readP2PDevSchClockActive."""
    raise NotImplementedError('ARM library required')

def readP2PDevSchInfor(*args, **kwargs):
    """Stub for readP2PDevSchInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevSchInforType(*args, **kwargs):
    """Stub for readP2PDevSchInforType."""
    raise NotImplementedError('ARM library required')

def readP2PDevSchItem(*args, **kwargs):
    """Stub for readP2PDevSchItem."""
    raise NotImplementedError('ARM library required')

def readP2PDevSchItemType(*args, **kwargs):
    """Stub for readP2PDevSchItemType."""
    raise NotImplementedError('ARM library required')

def readP2PDevUploadFileInfor(*args, **kwargs):
    """Stub for readP2PDevUploadFileInfor."""
    raise NotImplementedError('ARM library required')

def readP2PDevUploadFileItem(*args, **kwargs):
    """Stub for readP2PDevUploadFileItem."""
    raise NotImplementedError('ARM library required')

def readP2PDevUploadStatus(*args, **kwargs):
    """Stub for readP2PDevUploadStatus."""
    raise NotImplementedError('ARM library required')

def readP2PDevUserData(*args, **kwargs):
    """Stub for readP2PDevUserData."""
    raise NotImplementedError('ARM library required')

def readP2PDevUserItem(*args, **kwargs):
    """Stub for readP2PDevUserItem."""
    raise NotImplementedError('ARM library required')

def readP2PDevUserItemCount(*args, **kwargs):
    """Stub for readP2PDevUserItemCount."""
    raise NotImplementedError('ARM library required')

def readP2PDevWifiApItem(*args, **kwargs):
    """Stub for readP2PDevWifiApItem."""
    raise NotImplementedError('ARM library required')

def readP2PDevWifiInforData(*args, **kwargs):
    """Stub for readP2PDevWifiInforData."""
    raise NotImplementedError('ARM library required')

def readP2PDeviceMediaParams(*args, **kwargs):
    """Stub for readP2PDeviceMediaParams."""
    raise NotImplementedError('ARM library required')

def recordP2PDeviceStart(*args, **kwargs):
    """Stub for recordP2PDeviceStart."""
    raise NotImplementedError('ARM library required')

def recordP2PDeviceStartWithType(*args, **kwargs):
    """Stub for recordP2PDeviceStartWithType."""
    raise NotImplementedError('ARM library required')

def recordP2PDeviceStop(*args, **kwargs):
    """Stub for recordP2PDeviceStop."""
    raise NotImplementedError('ARM library required')

def reqDev4GInfor(*args, **kwargs):
    """Stub for reqDev4GInfor."""
    raise NotImplementedError('ARM library required')

def reqDevAPModeInfor(*args, **kwargs):
    """Stub for reqDevAPModeInfor."""
    raise NotImplementedError('ARM library required')

def reqDevAlarmConfig(*args, **kwargs):
    """Stub for reqDevAlarmConfig."""
    raise NotImplementedError('ARM library required')

def reqDevDDNSConfig(*args, **kwargs):
    """Stub for reqDevDDNSConfig."""
    raise NotImplementedError('ARM library required')

def reqDevEMailConfig(*args, **kwargs):
    """Stub for reqDevEMailConfig."""
    raise NotImplementedError('ARM library required')

def reqDevEMailTestRes(*args, **kwargs):
    """Stub for reqDevEMailTestRes."""
    raise NotImplementedError('ARM library required')

def reqDevFTPConfig(*args, **kwargs):
    """Stub for reqDevFTPConfig."""
    raise NotImplementedError('ARM library required')

def reqDevFTPTestRes(*args, **kwargs):
    """Stub for reqDevFTPTestRes."""
    raise NotImplementedError('ARM library required')

def reqDevIPInfor(*args, **kwargs):
    """Stub for reqDevIPInfor."""
    raise NotImplementedError('ARM library required')

def reqDevIRLedConfig(*args, **kwargs):
    """Stub for reqDevIRLedConfig."""
    raise NotImplementedError('ARM library required')

def reqDevMusic(*args, **kwargs):
    """Stub for reqDevMusic."""
    raise NotImplementedError('ARM library required')

def reqDevNTPConfig(*args, **kwargs):
    """Stub for reqDevNTPConfig."""
    raise NotImplementedError('ARM library required')

def reqDevSchInfor(*args, **kwargs):
    """Stub for reqDevSchInfor."""
    raise NotImplementedError('ARM library required')

def reqDevSchInforType(*args, **kwargs):
    """Stub for reqDevSchInforType."""
    raise NotImplementedError('ARM library required')

def reqDevSleepModeCfg(*args, **kwargs):
    """Stub for reqDevSleepModeCfg."""
    raise NotImplementedError('ARM library required')

def reqDevUploadFileInfor(*args, **kwargs):
    """Stub for reqDevUploadFileInfor."""
    raise NotImplementedError('ARM library required')

def reqDevUserInfor(*args, **kwargs):
    """Stub for reqDevUserInfor."""
    raise NotImplementedError('ARM library required')

def reqDevWifiInfor(*args, **kwargs):
    """Stub for reqDevWifiInfor."""
    raise NotImplementedError('ARM library required')

def reqP2PDev433MInfor(*args, **kwargs):
    """Stub for reqP2PDev433MInfor."""
    raise NotImplementedError('ARM library required')

def reqP2PDevSDCardRecConfig(*args, **kwargs):
    """Stub for reqP2PDevSDCardRecConfig."""
    raise NotImplementedError('ARM library required')

def reqP2PDeviceAVMedia(*args, **kwargs):
    """Stub for reqP2PDeviceAVMedia."""
    raise NotImplementedError('ARM library required')

def reqP2PDeviceRelayData(*args, **kwargs):
    """Stub for reqP2PDeviceRelayData."""
    raise NotImplementedError('ARM library required')

def reqP2PDeviceTalk(*args, **kwargs):
    """Stub for reqP2PDeviceTalk."""
    raise NotImplementedError('ARM library required')

def reqP2PSDCardAllFiles(*args, **kwargs):
    """Stub for reqP2PSDCardAllFiles."""
    raise NotImplementedError('ARM library required')

def requCKDoorCfg(*args, **kwargs):
    """Stub for requCKDoorCfg."""
    raise NotImplementedError('ARM library required')

def requCKFHQCfg(*args, **kwargs):
    """Stub for requCKFHQCfg."""
    raise NotImplementedError('ARM library required')

def requP2PDevSchClockActive(*args, **kwargs):
    """Stub for requP2PDevSchClockActive."""
    raise NotImplementedError('ARM library required')

def requP2PDeviceSnapshotImg(*args, **kwargs):
    """Stub for requP2PDeviceSnapshotImg."""
    raise NotImplementedError('ARM library required')

def resetDevSchInfor(*args, **kwargs):
    """Stub for resetDevSchInfor."""
    raise NotImplementedError('ARM library required')

def resetP2PDevAlarm(*args, **kwargs):
    """Stub for resetP2PDevAlarm."""
    raise NotImplementedError('ARM library required')

def resetP2PDevSchClockActive(*args, **kwargs):
    """Stub for resetP2PDevSchClockActive."""
    raise NotImplementedError('ARM library required')

def resetP2PDevUserInfor(*args, **kwargs):
    """Stub for resetP2PDevUserInfor."""
    raise NotImplementedError('ARM library required')

def resetP2PDeviceLastError(*args, **kwargs):
    """Stub for resetP2PDeviceLastError."""
    raise NotImplementedError('ARM library required')

def saveDevSchInfor(*args, **kwargs):
    """Stub for saveDevSchInfor."""
    raise NotImplementedError('ARM library required')

def saveDevSchInforType(*args, **kwargs):
    """Stub for saveDevSchInforType."""
    raise NotImplementedError('ARM library required')

def saveP2PDevSnapshot(*args, **kwargs):
    """Stub for saveP2PDevSnapshot."""
    raise NotImplementedError('ARM library required')

def saveP2PDevUserInfor(*args, **kwargs):
    """Stub for saveP2PDevUserInfor."""
    raise NotImplementedError('ARM library required')

def sendCKDoorCmd(*args, **kwargs):
    """Stub for sendCKDoorCmd."""
    raise NotImplementedError('ARM library required')

def sendCKFHQCmd(*args, **kwargs):
    """Stub for sendCKFHQCmd."""
    raise NotImplementedError('ARM library required')

def sendLanSehPackCmd(*args, **kwargs):
    """Stub for sendLanSehPackCmd."""
    raise NotImplementedError('ARM library required')

def sendP2PDeviceMediaCmd(*args, **kwargs):
    """Stub for sendP2PDeviceMediaCmd."""
    raise NotImplementedError('ARM library required')

def sendP2PDeviceTalkAudioData(*args, **kwargs):
    """Stub for sendP2PDeviceTalkAudioData."""
    raise NotImplementedError('ARM library required')

def sendP2PDeviceUserData(*args, **kwargs):
    """Stub for sendP2PDeviceUserData."""
    raise NotImplementedError('ARM library required')

def sendP2POtherData(*args, **kwargs):
    """Stub for sendP2POtherData."""
    raise NotImplementedError('ARM library required')

def setCKDoorCfg(*args, **kwargs):
    """Stub for setCKDoorCfg."""
    raise NotImplementedError('ARM library required')

def setCKFHQCfg(*args, **kwargs):
    """Stub for setCKFHQCfg."""
    raise NotImplementedError('ARM library required')

def setDevAccessPwd(*args, **kwargs):
    """Stub for setDevAccessPwd."""
    raise NotImplementedError('ARM library required')

def setDevIRLedControl(*args, **kwargs):
    """Stub for setDevIRLedControl."""
    raise NotImplementedError('ARM library required')

def setDevIRLedOn(*args, **kwargs):
    """Stub for setDevIRLedOn."""
    raise NotImplementedError('ARM library required')

def setDevMusicPlayMode(*args, **kwargs):
    """Stub for setDevMusicPlayMode."""
    raise NotImplementedError('ARM library required')

def setDevNTPSyncTime(*args, **kwargs):
    """Stub for setDevNTPSyncTime."""
    raise NotImplementedError('ARM library required')

def setDevP2PLinkMode(*args, **kwargs):
    """Stub for setDevP2PLinkMode."""
    raise NotImplementedError('ARM library required')

def setDevSDCardPlaySpeed(*args, **kwargs):
    """Stub for setDevSDCardPlaySpeed."""
    raise NotImplementedError('ARM library required')

def setDevSchItem(*args, **kwargs):
    """Stub for setDevSchItem."""
    raise NotImplementedError('ARM library required')

def setDevSchItemType(*args, **kwargs):
    """Stub for setDevSchItemType."""
    raise NotImplementedError('ARM library required')

def setDevSleepModeCfg(*args, **kwargs):
    """Stub for setDevSleepModeCfg."""
    raise NotImplementedError('ARM library required')

def setH264DecoderMode(*args, **kwargs):
    """Stub for setH264DecoderMode."""
    raise NotImplementedError('ARM library required')

def setP2PDecoderWorkMode(*args, **kwargs):
    """Stub for setP2PDecoderWorkMode."""
    raise NotImplementedError('ARM library required')

def setP2PDevAPModeInfor(*args, **kwargs):
    """Stub for setP2PDevAPModeInfor."""
    raise NotImplementedError('ARM library required')

def setP2PDevAccessUserDisabled(*args, **kwargs):
    """Stub for setP2PDevAccessUserDisabled."""
    raise NotImplementedError('ARM library required')

def setP2PDevAlarmConfig(*args, **kwargs):
    """Stub for setP2PDevAlarmConfig."""
    raise NotImplementedError('ARM library required')

def setP2PDevAlarmOpen(*args, **kwargs):
    """Stub for setP2PDevAlarmOpen."""
    raise NotImplementedError('ARM library required')

def setP2PDevDDNSConfig(*args, **kwargs):
    """Stub for setP2PDevDDNSConfig."""
    raise NotImplementedError('ARM library required')

def setP2PDevEMailConfig(*args, **kwargs):
    """Stub for setP2PDevEMailConfig."""
    raise NotImplementedError('ARM library required')

def setP2PDevFTPConfig(*args, **kwargs):
    """Stub for setP2PDevFTPConfig."""
    raise NotImplementedError('ARM library required')

def setP2PDevIPInfor(*args, **kwargs):
    """Stub for setP2PDevIPInfor."""
    raise NotImplementedError('ARM library required')

def setP2PDevIRLedConfig(*args, **kwargs):
    """Stub for setP2PDevIRLedConfig."""
    raise NotImplementedError('ARM library required')

def setP2PDevLastMsgID(*args, **kwargs):
    """Stub for setP2PDevLastMsgID."""
    raise NotImplementedError('ARM library required')

def setP2PDevNTPConfig(*args, **kwargs):
    """Stub for setP2PDevNTPConfig."""
    raise NotImplementedError('ARM library required')

def setP2PDevName(*args, **kwargs):
    """Stub for setP2PDevName."""
    raise NotImplementedError('ARM library required')

def setP2PDevParam(*args, **kwargs):
    """Stub for setP2PDevParam."""
    raise NotImplementedError('ARM library required')

def setP2PDevSDCardFormat(*args, **kwargs):
    """Stub for setP2PDevSDCardFormat."""
    raise NotImplementedError('ARM library required')

def setP2PDevSDCardRecCfg(*args, **kwargs):
    """Stub for setP2PDevSDCardRecCfg."""
    raise NotImplementedError('ARM library required')

def setP2PDevUserItem(*args, **kwargs):
    """Stub for setP2PDevUserItem."""
    raise NotImplementedError('ARM library required')

def setP2PDevWifiConnect(*args, **kwargs):
    """Stub for setP2PDevWifiConnect."""
    raise NotImplementedError('ARM library required')

def setP2PDevWifiDisconnect(*args, **kwargs):
    """Stub for setP2PDevWifiDisconnect."""
    raise NotImplementedError('ARM library required')

def setP2PDevicePlayFps(*args, **kwargs):
    """Stub for setP2PDevicePlayFps."""
    raise NotImplementedError('ARM library required')

def setP2PDeviceToSleep(*args, **kwargs):
    """Stub for setP2PDeviceToSleep."""
    raise NotImplementedError('ARM library required')

def setP2PDeviceType(*args, **kwargs):
    """Stub for setP2PDeviceType."""
    raise NotImplementedError('ARM library required')

def setVideoCodecLock(*args, **kwargs):
    """Stub for setVideoCodecLock."""
    raise NotImplementedError('ARM library required')

def setVideoEncodeInfor(*args, **kwargs):
    """Stub for setVideoEncodeInfor."""
    raise NotImplementedError('ARM library required')

def setupP2PDevicePushMsg(*args, **kwargs):
    """Stub for setupP2PDevicePushMsg."""
    raise NotImplementedError('ARM library required')

def startP2PDevWifiScan(*args, **kwargs):
    """Stub for startP2PDevWifiScan."""
    raise NotImplementedError('ARM library required')

def stopDevMusicPlay(*args, **kwargs):
    """Stub for stopDevMusicPlay."""
    raise NotImplementedError('ARM library required')

def stopDevSDCardRecFilePlay(*args, **kwargs):
    """Stub for stopDevSDCardRecFilePlay."""
    raise NotImplementedError('ARM library required')

def validDevManagePwd(*args, **kwargs):
    """Stub for validDevManagePwd."""
    raise NotImplementedError('ARM library required')

def wakeUpP2PDevice(*args, **kwargs):
    """Stub for wakeUpP2PDevice."""
    raise NotImplementedError('ARM library required')
