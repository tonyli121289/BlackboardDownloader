import errno
import json
import os
import pathlib
import re
import threading
import time
import urllib.parse
from datetime import datetime
from json import JSONEncoder
from pathlib import Path
from shutil import copyfile

import certifi
import pycurl
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait


class MyClass:
    def __init__(self, v):
        self.v = v

    def value(self):
        return self.v

    def __str__(self):
        return ""


class MyClassEncoder(json.JSONEncoder):
    def rt(self, x):
        pass

    def default(self, obj):
        if isinstance(obj, MyClass):
            return None
        if isinstance(obj, Path):
            return '/'.join([urllib.parse.quote(f, '') for f in obj.relative_to(self.rt(0)).parts])
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class MyThread(threading.Thread):
    def __init__(self, f):
        threading.Thread.__init__(self)
        self.f = f
        self.download_t = 0
        self.download_d = 0

    def run(self):
        c = pycurl.Curl()
        c.setopt(pycurl.URL, self.f['downloadLink'])
        c.setopt(pycurl.NOPROGRESS, False)
        c.setopt(pycurl.XFERINFOFUNCTION, self.progress)
        c.setopt(pycurl.FOLLOWLOCATION, True)
        c.setopt(pycurl.CAINFO, certifi.where())
        c.setopt(pycurl.COOKIEFILE, 'cookie.txt')
        filename = self.f['path']

        mkdir(filename)
        with open(filename, 'wb') as ff:
            c.setopt(pycurl.WRITEFUNCTION, ff.write)
            c.perform()
        c.close()

    def progress(self, download_t, download_d, upload_t, upload_d):
        # print("progress:", download_t, download_d, upload_t, upload_d)
        self.download_t = download_t
        self.download_d = download_d


def sizeof_fmt(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, 'Yi', suffix)


class MyThreadDispatcher(threading.Thread):
    def __init__(self, list):
        threading.Thread.__init__(self)
        self.downloadList = list
        self.msg = ""

    def run(self):
        all_downloaded = False
        while not all_downloaded:
            msg = ""
            all_downloaded = True
            msg += ("\n" * 50)
            downloaded = 0
            downloading = 0
            pending = 0
            for i in range(len(self.downloadList)):
                f = self.downloadList[i]
                if f['thread'].ident is None:
                    all_downloaded = False
                    if threading.active_count() < 20:
                        f['thread'].start()
                elif f['thread'].is_alive():
                    all_downloaded = False

                if f['thread'].ident is not None and f['thread'].is_alive():
                    msg += (
                        "\n{:4d} {}\n     Downloaded: {} of {}    ({:.2f}%)\n".format(i, f['fileName'],
                                                                                      sizeof_fmt(
                                                                                          f['thread'].download_d),
                                                                                      sizeof_fmt(
                                                                                          f['thread'].download_t),
                                                                                      100 * f['thread'].download_d /
                                                                                      f['thread'].download_t if f[
                                                                                                                    'thread'].download_t > 0 else 0))

                if f['thread'].ident is None:
                    pending += 1
                elif f['thread'].is_alive():
                    downloading += 1
                else:
                    downloaded += 1
            msg += ("\nDownloading: {} \tDownloaded: {} \t Pending: {}\n".format(downloading, downloaded, pending))
            msg += "threading.active_count() {}\n".format(threading.active_count())
            self.msg = msg


def mkdir(filename):
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise


def html_safe(s):
    return ''.join(["&#" + str(ord(a)) + ";" for a in s])


def get_data(url):
    global curl, baseurl
    # print("Getting data from ", url)
    curl.setopt(pycurl.URL, baseurl + url)
    return json.loads(curl.perform_rs())


def create_download_list(content):
    global downloadList
    if 'files' in content:
        for f in content['files']:
            f['path'] = get_path(content, f)
            f['downloadLink'] = baseurl + (
                '/learn/api/public/v1/courses/{}/contents/{}/attachments/{}/download'.format(
                    f['content'].value()['courseId'],
                    f['content'].value()['id'],
                    f['id']))
            downloadList.append(f)
    if 'contents' in content:
        for res in content['contents']:
            create_download_list(res)


def print_tree(res, indent=0):
    tab = '    '
    for s in res['contents']:
        print((tab * indent) + s['title'])
        if 'contents' in s:
            print_tree(s, indent + 1)
        if 'files' in s:
            for f in s['files']:
                print((tab * indent) + tab + "Attachment: " + f['fileName'])


def clear_file_name(s):
    return re.sub(r"[\[\\/:*?\"<>|\]]", "_", s)


def get_path(res, f=None):
    global root_folder

    if f is not None:
        if 'path' in f:
            return f['path']
        f['path'] = get_path(res) / clear_file_name(f['fileName'])
        return f['path']

    if 'path' in res:
        return res['path']

    if 'parent' not in res:
        res['path'] = root_folder / clear_file_name(res['course']['name']) / (
            "[{:0>3d}] {}".format(res['position'], clear_file_name(res['title'])))
        return res['path']

    res['path'] = get_path(res['parent'].value()) / (
        "[{:0>3d}] {}".format(res['position'], clear_file_name(res['title'])))
    return res['path']


driver = webdriver.Chrome()
driver.set_window_size(500, 900)
driver.get('https://elearn.cuhk.edu.hk/')
element = WebDriverWait(driver, 600).until(lambda x: x.find_element(By.ID, "submitButton"))
driver.execute_script('document.getElementById("header").innerHTML="<h1>Please Login to continue</h1>"')

if os.path.exists('login.txt'):
    file1 = open('login.txt', 'r')
    lines = file1.readlines()
    driver.execute_script('document.querySelector("#userNameInput").value="{}"'.format(lines[0].strip()))
    driver.execute_script('document.querySelector("#passwordInput").value="{}"'.format(lines[1].strip()))
    driver.execute_script('setTimeout(function(){document.querySelector("#submitButton").click()},1)')

baseurl = "https://blackboard.cuhk.edu.hk"

while not (driver.current_url.startswith(baseurl)):
    time.sleep(0.1)

root_folder = Path(os.getcwd()) / ("blackboard" + datetime.now().strftime("_%Y%m%d_%H%M%S"))
if isinstance(root_folder, pathlib.WindowsPath) and not str(root_folder).startswith("//?/"):
    root_folder = Path("//?/" + str(root_folder))

os.makedirs(root_folder)
for f in os.listdir("html"):
    copyfile(Path("html") / f, root_folder / f)

print("logged in")
cookies = driver.get_cookies()
driver.quit()
cookiesString = ""
for c in cookies:
    cookiesString += c['name'] + "=" + c['value'] + ";"

curl = pycurl.Curl()
curl.setopt(pycurl.COOKIE, cookiesString)
curl.setopt(pycurl.COOKIEJAR, 'cookie.txt')
curl.setopt(pycurl.COOKIEFILE, 'cookie.txt')
curl.setopt(pycurl.CAINFO, certifi.where())

print("Getting user_id...")
data = get_data('/learn/api/v1/users/me')
print("Hello {}, nice to meet you!".format(data['givenName']))
user_id = data['id']
print("Your user_id in blackboard is: {}".format(data['id']))
print()
print("Getting course list")

data = get_data("/learn/api/v1/users/{}/memberships?expand=course".format(user_id))

course_list = list(filter(lambda x: x['role'] == 'S', data['results']))
course_list.sort(key=lambda x: x['course']['displayId'])
for c in course_list:
    print("{:15s}{:30s}{}".format(c['courseId'], c['course']['courseId'], c['course']['name']))
    # print(c['courseId'],'\t','\t')

for c in course_list:
    print()
    print("Pre-processing ", c['course']['name'], end="...")
    data = get_data("/learn/api/public/v1/courses/{}/contents?recursive=true".format(c['courseId']))
    if 'status' in data:
        print("Cannot retrieve contents, skipping... Server response: ", data)
        continue

    all_contents = dict((x['id'], x) for x in data['results'])
    root_contents = []

    print("{:3d}/{:3d}".format(0, len(all_contents)), end='')
    i = 0
    for rid, r in all_contents.items():
        i += 1
        print("\b\b\b\b\b\b\b{:3d}/{:3d}".format(i, len(all_contents)), end='')
        r['course'] = c['course']
        r['courseId'] = c['courseId']
        data = get_data("/learn/api/public/v1/courses/{}/contents/{}/attachments".format(c['courseId'], rid))
        if "results" in data:
            r["files"] = data['results']
            for file in r["files"]:
                file["content"] = MyClass(r)
        #        print(r)
        if "parentId" in r:
            if "contents" not in all_contents[r["parentId"]]:
                all_contents[r["parentId"]]["contents"] = []
            all_contents[r["parentId"]]["contents"].append(r)
            r["parent"] = MyClass(all_contents[r["parentId"]])
        else:
            root_contents.append(r)
    c['contents'] = root_contents

for c in course_list:
    if 'contents' in c:
        print(c['course']['name'])
        print_tree(c)

downloadList = []

for c in course_list:
    if 'contents' in c:
        print(c['course']['name'])
        create_download_list(c)

curl.close()

filename = root_folder / "data.js"
mkdir(filename)

SubClass = type('SubClass', (MyClassEncoder, JSONEncoder), {'rt': lambda x, y: root_folder})

with open(filename, 'wt') as ff:
    ff.write("data=" + json.dumps(course_list, indent=4, cls=SubClass))

print("Files to be downloaded: {}".format(len(downloadList)))

print("creating thread")
for f in downloadList:
    f['thread'] = MyThread(f)

dispatcher = MyThreadDispatcher(downloadList)
dispatcher.start()

while dispatcher.is_alive():
    print(dispatcher.msg)
    time.sleep(2)
