import argparse
import github
import handle_photos
import jinja2
import logging
import constants
import os
import shutil
import sys
import unicodedata
import xlsxwriter
import yaml

import pdb

from jinja2 import Environment, PackageLoader, select_autoescape

parser = argparse.ArgumentParser(description="Top-level flags.")
parser.add_argument('--local-data', action='store_true')
parser.add_argument('--log-to-stdout', action='store_true')
parser.add_argument('--log-file', action='store')
parser.add_argument('--semester', action='store', choices=['spring', 'fall'], required=True)

g = github.Github(constants.GITHUB_ACCESS_TOKEN)
env = Environment(loader=PackageLoader('buildboard', 'templates'),
                    autoescape=select_autoescape(['html', 'xml']),
                    lstrip_blocks=True, trim_blocks=True)
# # # # # # #
CRIT_T = 'crit.html'
DIRECTORY_T = 'directory.html'
TEAM_CARD_T = 'team_card.html'
TEMPLATE_NAMES = [CRIT_T, DIRECTORY_T, TEAM_CARD_T]
TEMPLATES = {}
# # # # # # #

def get_yaml_path(team_name):
    return os.path.join(constants.PWD, constants.OUTPUT_DIR_NAME, constants.YAML_DIR_NAME, "%s.yaml" % team_name)

def get_yaml_doc(team_name):
    yaml_file = get_yaml_path(team_name)
    try:
        with open(yaml_file, 'r') as report_contents:
            doc = yaml.safe_load(report_contents)
            return doc
    except (yaml.parser.ParserError, yaml.scanner.ScannerError), e:
        logging.error('repo %s contains bad report.yaml file: %s' % (team_name, str(e)))
        return
    except IOError, e:
        logging.error('no file for repo %s' % team_name)

def save_team_files(team_constants):
    for team_name in team_constants:
        logging.info('getting yaml file for %s...' % team_name)
        try:
            repo_name = "%s/%s" % (constants.ORG_NAME, team_name)
            repo = g.get_repo(repo_name)
            team_yaml_file = get_yaml_path(team_name)
            with open(team_yaml_file, 'w') as outfile:
                yaml_file = repo.get_file_contents(constants.YAML_FILE_NAME)
                outfile.write(yaml_file.decoded_content)
        except github.GithubException, e:
            logging.error("There's a problem with the yaml file for %s: %s" % (team_name, str(e)))

def save_team_photos(team_constants):
    for team_name in team_constants:
        logging.info('downloading photos for %s...' % team_name)
        doc = get_yaml_doc(team_name)
        if doc:
            try:
                team_photo = doc['team']['picture']
                team_photo_url = handle_photos.get_photo_url(team_name, team_photo)
                team_photo_path = handle_photos.save_photo_path(constants.TEAM_PHOTOS_DIR_NAME, team_name, team_photo)
                handle_photos.save_photo(team_photo_url, team_photo_path, constants.PHOTO_SIZES[constants.TEAM_PHOTOS_DIR_NAME])
                doc['team']['picture'] = \
                    handle_photos.get_photo_path_for_web(handle_photos.save_photo_path(constants.TEAM_PHOTOS_DIR_NAME,
                                                        team_name, team_photo))
            except (KeyError, TypeError, IOError), e:
                logging.error('repo %s missing team photo: %s' % (team_name, str(e)))

            try:
                company_logo = doc['company']['logo']
                logo_url = handle_photos.get_photo_url(team_name, doc['company']['logo'])
                logo_path = handle_photos.save_photo_path(constants.COMPANY_LOGOS_DIR_NAME, team_name, company_logo)
                handle_photos.save_photo(logo_url, logo_path, constants.PHOTO_SIZES[constants.COMPANY_LOGOS_DIR_NAME])
                doc['company']['logo'] = \
                    handle_photos.get_photo_path_for_web(handle_photos.save_photo_path(constants.COMPANY_LOGOS_DIR_NAME,
                                                        team_name, company_logo))
            except (KeyError, TypeError, IOError), e:
                logging.error('repo %s missing company logo: %s' % (team_name, str(e)))

            try:
                roster = doc['team']['roster']
                for teammate in roster:
                    try:
                        individual_photo = teammate['picture']
                        sanified_email = teammate['email'].replace('@', '-')
                        individual_photo_url = handle_photos.get_photo_url(team_name, individual_photo)
                        individual_photo_path = handle_photos.save_photo_path(constants.INDIVIDUAL_PHOTOS_DIR_NAME, sanified_email, individual_photo)
                        handle_photos.save_photo(individual_photo_url, individual_photo_path, constants.PHOTO_SIZES[constants.INDIVIDUAL_PHOTOS_DIR_NAME])
                        teammate['picture'] = \
                            handle_photos.get_photo_path_for_web(handle_photos.save_photo_path(constants.INDIVIDUAL_PHOTOS_DIR_NAME,
                                                                sanified_email, individual_photo))

                    except (KeyError, TypeError, IOError, AttributeError), e:
                        # overwrite file with default member image for failed picture
                        teammate['picture'] = 'static/member3x.png'
                        logging.error('repo %s missing individual photo for member %s: %s' % (team_name, teammate['email'], str(e)))
            except (KeyError, TypeError), e:
                logging.error('repo %s has problems with team roster %s' % (team_name, str(e)))

            # save path updates to yaml file
            team_yaml_file = get_yaml_path(team_name)
            with open(team_yaml_file, 'w') as outfile:
                yaml.dump(doc, outfile, default_flow_style=False)

        else:
            logging.error("missing yaml: %s" % team_name)

def get_list(filename):
    with open(filename) as f:
        items = [item.strip() for item in f.readlines()]
        return items

def turn_tags_list_into_tags(tags):
    tag_names = {}
    for tag in tags:
        tag_names[tag.replace(' ', '-').replace('/', '-').lower()] = tag
    return tag_names

def turn_sections_list_into_dict(sections):
    sections_dict = {}
    for team in sections:
        t = team.split(',')
        sections_dict[t[0]] = t[1]
    return sections_dict

# TODO: deprecate in favor of the futuristic version
def get_crit_groups_ordered_by_room(teams_metadata):
    crit_rooms = {'A': {}, 'B' : {}}
    for team_line in teams_metadata:
        team = team_line.split("\t")

        team_name = team[3]
        team_crit_group = team[4]
        team_room = team[5]

        crit_group = crit_rooms[team_crit_group]
        if team_room not in crit_group:
            crit_group[team_room] = [team_name]
        else:
            crit_group[team_room].append(team_name)
    return crit_rooms

def load_teams_data(team_constants):
    team_data = {}
    for team_name in team_constants:
        team_doc = get_yaml_doc(team_name)
        if team_doc:
            team_doc['repo'] = team_name
            try:
                team_doc['tags'] = turn_tags_list_into_tags(team_doc['tags'])
            except (KeyError):
                logging.error('tags missing for team %s' % team_name)

            # check length of product narrative
            product_narrative = team_doc['product_narrative']
            if len(product_narrative) > 140:
                logging.warning('product narrative for team %s is too long: %d characters' % (team_name, len(product_narrative)))
        else:
            logging.error("missing yaml: %s" % team_name)
        team_data[team_name] = team_doc
    return team_data

def create_dir(dirname):
    if not os.path.exists(dirname):
        logging.info('creating new directory: %s' % dirname)
        os.makedirs(dirname)

def setup_output_directories(target_directory):
    output_dir = os.path.join(target_directory, constants.OUTPUT_DIR_NAME)
    create_dir(output_dir)

    # copy over static directory so that you can view files locally
    src = os.path.join(target_directory, constants.STATIC_DIR_NAME)
    dst = os.path.join(target_directory, constants.OUTPUT_DIR_NAME, constants.STATIC_DIR_NAME)
    if os.path.exists(dst):
		shutil.rmtree(dst)
    shutil.copytree(src, dst)

    for directory in constants.LOCAL_OUTPUT_DIRS:
        dir_path = os.path.join(output_dir, directory)
        create_dir(dir_path)

def create_crit_pages(crit_groups, teams):
    template = TEMPLATES[CRIT_T]
    if template:
        crit_A = template.render(group='Crit Group A',
                                rooms=crit_groups['A'],
                                teams=teams)

        crit_B = template.render(group='Crit Group B',
                                rooms=crit_groups['B'],
                                teams=teams)

        return (crit_A, crit_B)

def create_directory_page(teams, tags, semester):
    template = TEMPLATES[DIRECTORY_T]
    if template:
        return template.render(teams=teams, tags=tags, semester=semester)

def create_team_page(team, tags, semester):
    template = TEMPLATES[TEAM_CARD_T]
    if template:
        return template.render(team=team, tags=tags, semester=semester)

def pns_to_xlsx(sections, teams):
    workbook = xlsxwriter.Workbook(os.path.join(constants.PWD,
                                    constants.OUTPUT_DIR_NAME,
                                    constants.XLSX_FILE_NAME))
    worksheet = workbook.add_worksheet()
    columns = {'Team ID': 'A%d', 'Section': 'B%d', 'Company Name': 'C%d',
                'Team Members': 'D%d', 'Emails': 'E%d', 'Program': 'F%d',
                'Product Narrative': 'G%d'}
    row = 1
    for col in columns:
        worksheet.write(columns[col] % row, col)

    for team in teams:
        worksheet.write(columns['Team ID'] % row, team)
        worksheet.write(columns['Section'] % row, sections[team])
        team_data = teams[team]
        if team_data:
            worksheet.write(columns['Company Name'] % row, team_data['company']['name'])
            worksheet.write(columns['Product Narrative'] % row, team_data['product_narrative'])
            names, emails, programs, = '', '', ''
            try:
                team_members = team_data['team']['roster']
                for member in team_members:
                    try:
                        if member['name']:
                            names += member['name'] + '\n'
                        else:
                            logging.error('team %s missing name for some members' % team)
                        if member['email']:
                            emails += member['email'] + '\n'
                        else:
                            logging.error('team %s missing email for some members' % team)
                        if member['program']:
                            programs += member['program'] + '\n'
                        else:
                            logging.error('team %s missing program for some members' % team)
                    except (KeyError), e:
                        logging.error('team %s missing info for some members' % team)
            except (KeyError, TypeError), e:
                logging.error('error in roster for team %s' % team)


            worksheet.write(columns['Team Members'] % row, names)
            worksheet.write(columns['Emails'] % row, emails)
            worksheet.write(columns['Program'] % row, programs)
        else:
            logging.error('team %s has no roster' % team)
        row += 1
    workbook.close()

def create_book_data(teams):
    workbook = xlsxwriter.Workbook(os.path.join(constants.PWD,
                                    constants.OUTPUT_DIR_NAME,
                                    constants.BOOK_FILE_NAME))
    worksheet = workbook.add_worksheet()
    columns = {'Team Name': 'A%d', 'How Might We': 'B%d', 'Product Narrative': 'C%d',
                'Team Members': 'D%d', 'Team Programs': 'E%d', 'Company Logo': 'F%d',
                'Team Photo': 'G%d', 'Team ID': 'H%d'}
    row = 1
    for col in columns:
        worksheet.write(columns[col] % row, col)

    for team in teams:
        worksheet.write(columns['Team ID'] % row, team)
        team_data = teams[team]
        if team_data:
            names, programs, = '', ''
            try:
                team_members = team_data['team']['roster']
                for member in team_members:
                    try:
                        if member['name']:
                            names += member['name'] + '\n'
                        else:
                            logging.error('team %s missing name for some members' % team)
                        if member['program']:
                            programs += member['program'] + '\n'
                        else:
                            logging.error('team %s missing program for some members' % team)
                    except (KeyError), e:
                        logging.error('team %s missing info for some members' % team)
            except (KeyError, TypeError), e:
                logging.error('error in roster for team %s' % team)
            worksheet.write(columns['Team Members'] % row, names)
            worksheet.write(columns['Team Programs'] % row, programs)
            try:
                worksheet.write(columns['Team Name'] % row, team_data['company']['name'])
            except (KeyError), e:
                logging.error('error in company name for team %s' % team)
            try:
                worksheet.write(columns['Product Narrative'] % row, team_data['product_narrative'])
            except (KeyError), e:
                logging.error('error in product_narrative for team %s' % team)
            try:
                worksheet.write(columns['How Might We'] % row, team_data['product_hmw'])
            except (KeyError), e:
                logging.error('error in product_hmw for team %s' % team)
            try:
                worksheet.write(columns['Company Logo'] % row, team_data['company']['logo'])
            except (KeyError), e:
                logging.error('error in company logo for team %s' % team)
            try:
                worksheet.write(columns['Team Photo'] % row, team_data['team']['picture'])
            except (KeyError), e:
                logging.error('error in team photo for team %s' % team)
        else:
            logging.error('team %s has no roster' % team)
        row += 1
    workbook.close()

# TODO: deprecate this in favor of a futuristic model
def build_crit_pages(teams, teams_metadata):
    def create_crit_group_pages(group, data):
        crit_file = os.path.join(constants.PWD, constants.OUTPUT_DIR_NAME, constants.CRIT_FILE_NAME % group)
        write_template_output_to_file(data, crit_file)
        output_crit_groups_xlsx(group, crit_groups[group], teams)

    crit_groups = get_crit_groups_ordered_by_room(teams_metadata)
    crit_groups_data = create_crit_pages(crit_groups, teams)
    if crit_groups:
        create_crit_group_pages('A', crit_groups_data[0])
        create_crit_group_pages('B', crit_groups_data[1])

def build_new_site_design(teams, semester):
    tags_file = os.path.join(constants.PWD, constants.TAGS_FILE_NAME)
    tags = turn_tags_list_into_tags(get_list(tags_file))

    directory = create_directory_page(teams, tags, semester)
    directory_file = os.path.join(constants.PWD, constants.OUTPUT_DIR_NAME, constants.DIRECTORY_PAGE_NAME)
    write_template_output_to_file(directory, directory_file)

    for team in teams:
        team_content = teams[team]
        team_page = create_team_page(team_content, tags, semester)
        team_page_file = os.path.join(constants.PWD, constants.OUTPUT_DIR_NAME, constants.TEAM_PAGES_DIR_NAME,
                                        "%s.html" % team)
        write_template_output_to_file(team_page, team_page_file)

def create_all_pages(local_data, semester):
    setup_output_directories(constants.PWD)

    teams_file = os.path.join(constants.PWD, constants.TEAMS_FILE_NAME)
    team_names = get_list(teams_file)

    sections_file = os.path.join(constants.PWD, constants.SECTIONS_FILE_NAME)
    sections = turn_sections_list_into_dict(get_list(sections_file))

    if not local_data:
        save_team_files(team_names)
        save_team_photos(team_names)

    teams = load_teams_data(team_names)
    build_new_site_design(teams, semester)
    pns_to_xlsx(sections, teams)
    create_book_data(teams)

def write_template_output_to_file(output, dst):
    if output:
        with open(dst, 'w') as outfile:
            outfile.write(unicodedata.normalize('NFKD', output).encode('ascii','ignore'))
        logging.info(outfile)
    else:
        logging.error('there is no content for file %s' % dst)

def config_logging(args):
    # config basics
    format_style = '%(asctime)s - %(levelname)s - %(message)s'
    if args.log_file:
        filename = args.log_file
    else:
        # use default name
        filename = 'output.log'
    logging.basicConfig(filename=filename, format=format_style, level=logging.INFO)

    # if you're also logging to stdout, set up additional handler
    if args.log_to_stdout:
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(format_style)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

def verify_templates():
    existing_templates = env.list_templates()
    for template_name in TEMPLATE_NAMES:
        if template_name not in existing_templates:
            logging.error('%s template is missing' % template_name)
            TEMPLATES[template_name] = None
        else:
            template = env.get_template(template_name)
            TEMPLATES[template_name] = template

if __name__ == '__main__':
    args = parser.parse_args()
    config_logging(args)
    verify_templates()
    create_all_pages(args.local_data, args.semester)
