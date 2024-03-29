# JSOn service
from django.http import HttpResponse
from pprint import pprint

import keystoneclient.v2_0.client as ksclient
import glanceclient,yaml

from django.views.decorators.csrf import csrf_exempt
from imagedist.models import site,user,credential

import json,datetime,threading,time,os

stream = open("glint_services.yaml", 'r')
cfg = yaml.load(stream)

_auth_url=cfg['auth_url']
_glance_url=cfg['glance_url']
_root_site=cfg['root_site']

def savi_fix(keystone,glance_ep):
    if 'iam.savitestbed.ca' in keystone.auth_url:
        return glance_ep.replace('/v1','')
    return glance_ep    

def _get_images(keystone):
    glance_ep = keystone.service_catalog.url_for(service_type='image',endpoint_type='publicURL')
    glance_ep = savi_fix(keystone,glance_ep)
    glance = glanceclient.Client('1',glance_ep,token=keystone.auth_token)
    images = glance.images.list()
    return images
        
@csrf_exempt
def getImages(request):
    try:
        keystone = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        print "keystone info %s"%keystone.auth_tenant_id
        ret_obj = {}
        ret_obj['rows']=[]
        
        usr = _auto_register_user(request)
        images = _get_images(keystone)
        
        json_msg = {}
        rows = []
        sites = []
        sites.append({"name":"%s"%(_root_site),"tenent":"%s"%(request.POST['USER_TENANT'])})
        for index,image in enumerate(images):
            #print "found Image locally %s"%image
            img_obj = {}
            img_obj['image']=image.name
            img_obj['disk_format']=image.disk_format
            img_obj['container_format']=image.container_format
            site_list = []
            if image.owner == keystone.auth_tenant_id:
                site_list.append({"name":"%s"%(_root_site),"tenent":"%s"%(request.POST['USER_TENANT']),"is_public":"%s"%image.is_public,"is_owner":"True"})
            else:
                site_list.append({"name":"%s"%(_root_site),"tenent":"%s"%(request.POST['USER_TENANT']),"is_public":"%s"%image.is_public,"is_owner":"False"})
            img_obj['sites']=site_list
            rows.append(img_obj)
        
        
        creds=credential.objects.filter(user=usr)
        for cred in creds:
            try:
                
                _keystone_ = ksclient.Client(username=cred.un,password=cred.pw,tenant_name=cred.tenent,auth_url="%s:%s/v2.0"%(cred.site.url,cred.site.authport))
                images = _get_images(_keystone_)
                sites.append({"name":"%s"%(cred.site.name),"tenent":"%s"%(cred.tenent)})
                for index,image in enumerate(images):
                    #print "found %s"%image.name
                    inserted=False
                    for row in rows:
                        #print "In rows found image %s"%row['image']
                        if row['image'] == image.name:
                            if image.owner == _keystone_.auth_tenant_id:
                                row['sites'].append({"name":"%s"%(cred.site.name),"tenent":"%s"%(cred.tenent),"is_public":"%s"%image.is_public,"is_owner":"True"})
                            else:
                                row['sites'].append({"name":"%s"%(cred.site.name),"tenent":"%s"%(cred.tenent),"is_public":"%s"%image.is_public,"is_owner":"False"})
                            inserted=True
                        
                    if not inserted:
                        #print "found a new Image list" 
                        img_obj = {}
                        img_obj['image']=image.name
                        img_obj['disk_format']=image.disk_format
                        img_obj['container_format']=image.container_format
                        site_list = []
                        if image.owner == _keystone_.auth_tenant_id:
                            site_list.append({"name":"%s"%(cred.site.name),"tenent":"%s"%(cred.tenent),"is_public":"%s"%image.is_public,"is_owner":"True"})
                        else:
                            site_list.append({"name":"%s"%(cred.site.name),"tenent":"%s"%(cred.tenent),"is_public":"%s"%image.is_public,"is_owner":"False"})
                        img_obj['sites']=site_list
                        rows.append(img_obj)
            except:
                print "Error Occurred getting images from %s"%cred.site.url
        
        json_msg['sites']=sites
        json_msg['rows']=rows
        
        respstr = json.dumps(json_msg)
        
        return HttpResponse(respstr)
    except:
        return HttpResponse("Invalid Credentials")

image_copies=[]
thread_id=0


def touch(path):
    os.makedirs(path)

class imageremovehandler():
    jsonMsgObj=''
    status="incomplete"
    local_user=''
    local_tenent=''
    
    def __init__(self,request,jsonMsgObj):
        self.jsonMsgObj=jsonMsgObj
        self.local_user=request.POST['USER_ID']
        self.local_tenent=request.POST['USER_TENANT']
     
    def getstatus(self):
        return self.status   
    
    def start(self):
        print "create thread and start image removal work"
        self.thread = threading.Thread(target=self.remove_image,args=[] )
        self.thread.start()
        
    def remove_image(self):
        print "remove image as per jsonMsgObj"
        try:
            keystone_src=''
            if self.jsonMsgObj['img_src_site'] ==_root_site:
                #print "remove from Rat is not allowed"
                self.status="complete"
                return
            else:
                src_site_name = site.objects.filter(name=self.jsonMsgObj['img_src_site'])
                user_name = user.objects.filter(username=self.local_user,tenent=self.local_tenent)
                print "now generate credentials"
                cred = credential.objects.filter(user=user_name,site=src_site_name,tenent=self.jsonMsgObj['image_src_tenent'])
                print "now get keystoe client"
                keystone_src = ksclient.Client(auth_url="%s:%s/v2.0"%(src_site_name[0].url,src_site_name[0].authport),username=cred[0].un,password=cred[0].pw,tenant_name=cred[0].tenent)
            print "now create service ep"
            glance_ep_src = keystone_src.service_catalog.url_for(service_type='image',endpoint_type='publicURL')
            glance_ep_src = savi_fix(keystone_src,glance_ep_src)
            glance_src = glanceclient.Client('1',glance_ep_src,token=keystone_src.auth_token)
            print "now list images"
            images = glance_src.images.list()
    #image = images.find()
            for index,image in enumerate(images):
                #pprint('Images:%s:%s' %(index,image))
                if image.name == self.jsonMsgObj['image_name']:
                    pprint("found image name %s" % image.name)
                    image.delete()
                    pprint("done deleting image")
            self.status="complete"
        except:
            print "error occurred removing image"
        
    
class imagecopyhandler():
    status="incomplete"
    thread=''
    img_name=''
    disk_format=''
    container_format=''
    source_site=''
    source_tenent=''
    remote_site=''
    remote_tenent=''
    count=0
    copy_from_root=False
    local_user=''
    user_token=''
    local_tenent=''
    
    
    def __init__(self,request,diskformat,containerformat,imagename,remotesite,remotetenent,sourcesite,sourcetenent):
        self.container_format=containerformat
        self.disk_format=diskformat
        self.img_name=imagename
        self.remote_site=remotesite
        self.source_site=sourcesite
        self.remote_tenent=remotetenent
        self.source_tenent=sourcetenent
        self.local_user=request.POST['USER_ID']
        self.user_token=request.POST['USER_TOKEN']
        self.local_tenent=request.POST['USER_TENANT']
        if sourcesite == _root_site:
            self.copy_from_root=True
        else:
            self.copy_from_root=False
        
    def getstatus(self):
        self.count=self.count+1
        return self.status
    
    def start(self):
        print "create thread and start work"
        self.thread = threading.Thread(target=self.transfer_image,args=[self.img_name,self.remote_site,self.source_site] )
        self.thread.start()
    
    def transfer_image(self,imageName,remoteSite,sourceSite):
        print "start image transfer %s from %s:%s to %s:%s"%(self.img_name,self.source_site,self.source_tenent,self.remote_site,self.remote_tenent)   
        directory=''
        
        try:
            keystone_src=''
            if self.source_site ==_root_site:
                print "copy from Rat is source"
                keystone_src = ksclient.Client(token=self.user_token,tenant_name=self.local_tenent,auth_url=_auth_url)
            else:
                src_site_name = site.objects.filter(name=self.source_site)
                user_name = user.objects.filter(username=self.local_user,tenent=self.local_tenent)
                
                cred = credential.objects.filter(user=user_name,site=src_site_name,tenent=self.source_tenent)
                print "copy from other %s:%s/v2.0"%(src_site_name[0].url,src_site_name[0].authport)
                print "using creds %s:%s,%s"%(cred[0].un,cred[0].pw,cred[0].tenent)
                keystone_src = ksclient.Client(auth_url="%s:%s/v2.0"%(src_site_name[0].url,src_site_name[0].authport),username=cred[0].un,password=cred[0].pw,tenant_name=cred[0].tenent)
            
            glance_ep_src = keystone_src.service_catalog.url_for(service_type='image',endpoint_type='publicURL')
            glance_ep_src = savi_fix(keystone_src,glance_ep_src) 
            glance_src = glanceclient.Client('1',glance_ep_src,token=keystone_src.auth_token)
            
            images = glance_src.images.list()
            img_id=''
            for img in images:
                if img.name == self.img_name:
                    img_id=img.id
                
            image_src = glance_src.images.get(img_id)
            img_data = glance_src.images.data(image_src,True)
            directory = "/home/rd/imgcopytmp/%s/%s_%s/"%(img_id,self.remote_site,self.remote_tenent)
            touch(directory)
            with open('%s/%s'%(directory,self.img_name),'wb') as f:
                for data_chunk in img_data:
                    f.write(data_chunk)
            
            print "image download complete"
        except:
            print "error occurred on download ignore"       
       
        try:
            print "Create Image Remote UPLOAD %s,%s,%s to %s"%(self.disk_format,self.container_format,self.img_name,self.remote_site)
            
            keystone_dest=''
            if self.remote_site ==_root_site:
                print "copy to Rat is dest"
                keystone_dest = ksclient.Client(token=self.user_token,tenant_name=self.local_tenent,auth_url=_auth_url)
            else:
                remote_site_name = site.objects.filter(name=self.remote_site)
                user_name = user.objects.filter(username=self.local_user,tenent=self.local_tenent)
                
                cred = credential.objects.filter(user=user_name,site=remote_site_name,tenent=self.remote_tenent)
                keystone_dest = ksclient.Client(auth_url="%s:%s/v2.0"%(remote_site_name[0].url,remote_site_name[0].authport),username=cred[0].un,password=cred[0].pw,tenant_name=cred[0].tenent)
                
            glance_ep_dest = keystone_dest.service_catalog.url_for(service_type='image',endpoint_type='publicURL')
            glance_ep_dest = savi_fix(keystone_dest,glance_ep_dest)
            glance_dest = glanceclient.Client('1',glance_ep_dest,token=keystone_dest.auth_token)
            
            file_loc='%s%s'%(directory,self.img_name)
            fimage = open(file_loc)
            glance_dest.images.create(name=self.img_name,is_public="False",disk_format=self.disk_format,container_format=self.container_format,data=fimage)
            
            print "done update with data upload"
            
        except:
            print "error uploading image occurred"
            
        print "done remote file transfer"
        self.status="complete"
        
@csrf_exempt
def save(request):
    try:
        jsonMsg = request.POST['jsonMsg']
        user = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        
        jsonMsgObj = json.loads(jsonMsg)
       
        if jsonMsgObj['op'] == "add_img":
            img_hndlr = imagecopyhandler(request,jsonMsgObj['disk_format'],jsonMsgObj['container_format'],jsonMsgObj['image_name'],jsonMsgObj['image_dest'],jsonMsgObj['image_dest_tenent'],jsonMsgObj['img_src'][0]['site_name'],jsonMsgObj['img_src'][0]['tenent_name'])
            image_copies.append(img_hndlr)
            idx = image_copies.index(img_hndlr, )
            print "k add image now and return thread id %s"%idx
            img_hndlr.start()
            return HttpResponse('{"thread_id":%s}'%idx)
        elif jsonMsgObj['op'] == "rem_img":
            print "try to remove image"
            img_hndlr = imageremovehandler(request,jsonMsgObj)
            image_copies.append(img_hndlr)
            idx = image_copies.index(img_hndlr,)
            img_hndlr.start()
            return HttpResponse('{"thread_id":%s}'%idx)
        elif jsonMsgObj['op'] == "thread_update":
            jsonMsgObj['status']=image_copies[jsonMsgObj['thread_id']].getstatus()
            return HttpResponse(json.dumps(jsonMsgObj))
        
        
        return HttpResponse("Unkown operation %s"%jsonMsg['op'])
    except:
        return HttpResponse("Invalid Save Credentials")

@csrf_exempt
def credentials(request):
    try:
        user = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        pprint("glint recieved a valid user token for %s"%request.POST['USER_ID'])
        user_name=request.POST['USER_ID']
        return HttpResponse("credentials: user is valid")
    except:
        return HttpResponse("Invalid Credentials")

class Object(object):
    pass

@csrf_exempt
def listsites(request):
    print "try to list sites"
    try:
        user = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        s = site.objects.filter()
        
        response = []
        for sobj in s:
            sobjstr = '{"name":"%s","url":"%s","authport":"%s","type":"%s","pk":"%s"}'%(sobj.name,sobj.url,sobj.authport,sobj.type,sobj.pk)
            response.append(sobjstr)
        respstr = json.dumps(response)
        
        return HttpResponse(respstr)
    except:
        return HttpResponse("Invalid Credentials")

@csrf_exempt
def deletesite(request):
    try:
        user = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        #pprint("glint recieved a valid user token for %s"%request.POST['USER_ID'])
        user_name=request.POST['USER_ID']
        site_id = request.POST['SITE_ID']
        #print "create site with %s"%site_data
        s=site.objects.filter(pk=site_id)
        s.delete()
        #s=site(name=site_data['name'],url=site_data['url'],authport=site_data['port'],type=site_data['disk_format'])
        #s.save()
        #print "create site complete"
        return HttpResponse("sites: site deleted %s"%site_id)
    except:
        return HttpResponse("Invalid Credentials")
    
    
@csrf_exempt
def createsite(request):
    try:
        user = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        #pprint("glint recieved a valid user token for %s"%request.POST['USER_ID'])
        user_name=request.POST['USER_ID']
        site_data = eval(request.POST['SITEDATA'])
        #print "create site with %s"%site_data
        s=site(name=site_data['name'],url=site_data['url'],authport=site_data['port'],type=site_data['disk_format'])
        s.save()
        #print "create site complete"
        return HttpResponse("sites: create is valid")
    except:
        return HttpResponse("Invalid Credentials")

def _auto_register_user(request):
    user_name=request.POST['USER_ID']
    token=request.POST['USER_TOKEN']
    tenant_name=request.POST['USER_TENANT']
    usr = user.objects.filter(username=user_name,tenent=tenant_name)
    print "found %s"%usr
    if len(usr) is 0:
        print "User not seen before adding entry to db"
        usr = user(username=user_name,tenent=tenant_name,token=token,lastlogin=datetime.datetime.now())
        usr.save()
        return usr
    else:
        print "User exists, so update date time"
        usr[0].lastlogin = datetime.datetime.now()
        usr[0].token = token
        usr[0].save()
        return usr[0]
    
@csrf_exempt
def addcredential(request):
    try:
        user = ksclient.Client(token=request.POST['USER_TOKEN'],tenant_name=request.POST['USER_TENANT'],auth_url=_auth_url)
        #pprint("glint recieved a valid user token for %s"%request.POST['USER_ID'])
        cred_data = eval(request.POST['CREDDATA'])
           
        usr = _auto_register_user(request)
        
        #print "find site with %s"%cred_data['site_id']
        ste = site.objects.filter(pk=cred_data['site_id'])
        
        #print "add credential with %s"%cred_data
        
        #user site and tenent need to be unique
        
        cred = credential.objects.filter(user=usr,site=ste,tenent=cred_data['tenent'])
        if len(cred) is 0:
            print "credentials does not exist for this user/site/tenent combo so create it"
            
            cred = credential(user=usr,site=ste[0],tenent=cred_data['tenent'],un=cred_data['username'],pw=cred_data['password'])
            
            cred.save()
        else:
            print "credentials exists for this user/site/tenent combo, assume an update"
            cred[0].un=cred_data['username']
            cred[0].pw=cred_data['password']
            cred[0].save()
        
        return HttpResponse("sites: add credential")
    except:
        return HttpResponse("Invalid Credentials")
    
