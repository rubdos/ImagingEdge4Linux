#!/bin/python3

from xml.dom import minidom
from urllib.parse import urlparse, unquote
from gi.repository import GLib
import os
import requests
import argparse

__author__    = 'Georg Sieber'
__copyright__ = '(c) 2024'


class ImagingEdge:
    ROOT_DIR_PUSH = 'PushRoot'
    ROOT_DIR_PULL = 'PhotoRoot'

    DEFAULT_IP    = '192.168.122.1'
    DEFAULT_PORT  = '64321'

    def __init__(self, address, port, output_dir, debug):
        self.address = address
        self.port = port
        self.output_dir = output_dir
        self.debug = debug

    def getServiceInfo(self):
        response = requests.get('http://'+self.address+':'+self.port+'/DmsDescPush.xml')
        return response.text

    def startTransfer(self):
        # display "Transferring" on the camera display (only works in push mode)
        response = requests.post(
            'http://'+self.address+':'+self.port+'/upnp/control/XPushList',
            headers = {
                'SOAPACTION': '"urn:schemas-sony-com:service:XPushList:1#X_TransferStart"',
                'Content-Type': 'text/xml; charset="utf-8"',
            },
            data = ('<?xml version="1.0" encoding= "UTF-8"?>'
                +'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                +'<s:Body>'
                +'<u:X_TransferStart xmlns:u="urn:schemas-sony-com:service:XPushList:1"></u:X_TransferStart>'
                +'</s:Body>'
                +'</s:Envelope>')
        )
        if(self.debug):
            print('Transfer start response:', response.status_code, response.text)

    # get dir contents
    def getDirectoryContent(self, dir, dirname):
        response = requests.post(
            'http://'+self.address+':'+self.port+'/upnp/control/ContentDirectory',
            headers = {
                'SOAPACTION': '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"',
                'Content-Type': 'text/xml; charset="utf-8"',
            },
            data = ('<?xml version="1.0"?>'
                +'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
                +'<s:Body>'
                +'<u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
                +'<ObjectID>'+dir+'</ObjectID>'
                +'<BrowseFlag>BrowseDirectChildren</BrowseFlag>'
                +'<Filter>*</Filter>'
                +'<StartingIndex>0</StartingIndex>'
                +'<RequestedCount>9999</RequestedCount>'
                +'<SortCriteria></SortCriteria>'
                +'</u:Browse>'
                +'</s:Body>'
                +'</s:Envelope>')
        )
        if(self.debug):
            print('Dir content response:', response.status_code, response.text)
        if(response.status_code != 200):
            raise Exception('Failed to get dir content:', dir)

        dom = minidom.parseString(response.text)
        for element in dom.getElementsByTagName('Result'):
            # yes, no joke: there is a XML string encoded inside the <Result>, so we need to parse a second time
            if(self.debug):
                print('Dir content inner response:', element.firstChild.nodeValue)
            dom2 = minidom.parseString(element.firstChild.nodeValue)

            # yay, a container (sub directory)
            for element2 in dom2.getElementsByTagName('container'):
                dirname = element2.getElementsByTagName('dc:title')[0].firstChild.nodeValue
                print('Entering subdir:', element2.attributes['id'].value, dirname)
                self.getDirectoryContent(element2.attributes['id'].value, dirname)

            # yay, an image (item)
            for element2 in dom2.getElementsByTagName('item'):
                # get name and download path
                filename = element2.getElementsByTagName('dc:title')[0].firstChild.nodeValue
                filepath = self.output_dir+'/'+dirname+'/'+filename
                # find the best resolution of this item
                lastSize = 0; lastResolution = 0; url = None
                for element3 in element2.getElementsByTagName('res'):
                    size = 0; resolution = 0
                    if('size' in element3.attributes):
                        size = int(element3.attributes['size'].value)
                    if('resolution' in element3.attributes):
                        resolution = element3.attributes['resolution'].value
                    if(size > lastSize):
                        url = element3.firstChild.nodeValue
                        lastSize = size
                        lastResolution = resolution
                # download the best resolution
                if(url):
                    self.downloadFile(url, filepath)
                else:
                    print('Unable to find a download candidate!')

    def downloadFile(self, url, filepath=None):
        # fallback file name
        if(not filepath):
            filepath = self.output_dir+'/'+unquote(urlparse(url).path)
        # skip if exists
        if(os.path.isfile(filepath)):
            print('Skip existing file:', filepath)
            return
        # make dirs
        if(not os.path.isdir(os.path.dirname(filepath))):
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # do the download
        print('Downloading:', url, ' -> ', filepath)
        with requests.get(url, stream=True) as r:
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

def main():
    defaultImgDir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES) + '/ImagingEdge4Linux'

    parser = argparse.ArgumentParser(epilog=__copyright__+' '+__author__+' - https://georg-sieber.de')
    parser.add_argument('-a', '--address', default=ImagingEdge.DEFAULT_IP, help='IP address of your camera')
    parser.add_argument('-p', '--port', default=ImagingEdge.DEFAULT_PORT, help='Port of your camera')
    parser.add_argument('-o', '--output-dir', default=defaultImgDir, help='Directory where to save the downloaded files')
    parser.add_argument('--debug', default=False, action='store_true', help='Show debug output')
    parser.add_argument('--version', action='store_true', help='Print version and exit')
    args = parser.parse_args()

    ie = ImagingEdge(args.address, args.port, args.output_dir, args.debug)
    if(args.debug):
        print(ie.getServiceInfo())
    ie.startTransfer()
    try:
        # user selected "Choose images on camera"
        ie.getDirectoryContent(ie.ROOT_DIR_PUSH, ie.ROOT_DIR_PUSH)
    except Exception as e:
        # user selected "Choose images on computer" (= access to all images)
        ie.getDirectoryContent(ie.ROOT_DIR_PULL, ie.ROOT_DIR_PULL)

if(__name__ == '__main__'):
    main()
