import os

from names import *

def get_photo_url(repo_name, img_name):
    return 'https://raw.githubusercontent.com/%s/%s/master/%s' % (ORG_NAME, repo_name, img_name)

def save_photo_path(output_dir_name, repo_name, img_name):
    return os.path.join(PWD, OUTPUT_DIR_NAME, output_dir_name,
                        "%s-%s" % (repo_name, img_name))

def get_photo_path_for_web(photo_path):
    web_path = os.path.relpath(photo_path, os.path.join(PWD, OUTPUT_DIR_NAME))
    return web_path

def save_photo(url, output_path):
    print 'saving %s' % os.path.basename(output_path)
    access_token = 'token %s' % GITHUB_ACCESS_TOKEN
    response = requests.get(url, stream=True, headers={'Authorization': access_token})
    with open(output_path, 'wb') as outfile:
        shutil.copyfileobj(response.raw, outfile)
    return get_photo_path_for_web(output_path)