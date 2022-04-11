import os
from typing import Optional

import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import json
from collections import namedtuple
import logging
from datamodel_code_generator import InputFileType, generate
from pathlib import Path
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__file__)

RawProperty = namedtuple('RawProperty', ['name', 'type', 'description'])
RawBlock = namedtuple('RawBlock', ['name', 'raw_properties'])
Api = namedtuple("Api", ['name', 'endpoints'])
Endpoint = namedtuple('Endpoint', ['name', 'href'])

CONVERT = {
    'string': 'string',
    'int': 'integer',
    'long': 'integer',
    'float': 'number',
    'boolean': 'boolean'
}

PARSED = []


def parse_type(type_: str) -> dict:
    # convert the types from the RiotApi to the Pydantic types
    if n := CONVERT.get(type_):
        return {"type": n}
    # handel the list / array types
    if type_.startswith("List") or type_.startswith("Set"):
        return parse_list(type_)
    # handel custom object types
    return {"$ref": f"#/definitions/{type_}"}


def parse_list(type_: str) -> dict:
    list_ = {"type": 'array'}
    # remove List[...] or Set[..] from the string to get the type of the items in the list
    type_ = type_.split("[")[1]
    type_ = type_[:-1]
    # parse type of the list items
    list_["items"] = [parse_type(type_)]
    return list_


def parse_property(raw_property: RawProperty) -> dict:
    # parse type
    property_ = parse_type(raw_property.type)
    # add description if exists
    if raw_property.description:
        property_['description'] = raw_property.description
    return {raw_property.name: property_}


def parse_block_response_body(block) -> Optional[RawBlock]:
    # name of the class
    if name := block.find("h5"):
        name = name.text.strip()
        # check is class got already parsed
        if name not in PARSED:
            PARSED.append(name)
            raw_block = RawBlock(name, [])
            body = block.find("tbody")

            # iter through the table and extract name, type and description
            for row in body.find_all("tr"):
                name, type_, description = [x.text.strip() for x in row.find_all("td")][:3]
                raw_block.raw_properties.append(RawProperty(name, type_, description))
            return raw_block


def parse_response_block_to_definition(block: RawBlock) -> dict:
    # create dict definition dict with the name of the definition and an empty properties dict
    definition = {block.name: {"properties": {}}}
    for raw_property in block.raw_properties:
        # update the properties
        definition[block.name]["properties"].update(parse_property(raw_property))
    return definition


def parse_response_block_to_schema(block: RawBlock) -> dict:
    schema = {"$schema": "http://json-schema.org/draft-07/schema#", "title": block.name, "type": "object",
              "properties": {}}
    for raw_property in block.raw_properties:
        schema["properties"].update(parse_property(raw_property))
    return schema


def parse_entry(entry) -> tuple[str, str, str]:
    m = entry.find('a')
    span = m.find("span")
    name = span.text.strip()
    api_name = m.get('api-name')
    href = m.get('href')
    name, api_name, href = name.strip(), api_name.strip(), href.strip()
    return name, api_name, href


def parse_entries(url: str = 'https://developer.riotgames.com/apis', parser='lxml'):
    r = requests.get(url)
    site = BeautifulSoup(r.text, features=parser)
    match = site.find('div', class_="scrollable-container")
    match = match.find('ul')
    return match.find_all('li')


def get_api_endpoints(url: str, parser: str) -> dict[str, Api]:
    apis = {}
    for entry in parse_entries(url, parser):
        name, api_name, href = parse_entry(entry)
        if n := apis.get(name):
            n.endpoints.append(Endpoint(api_name, href))
        else:
            apis[name] = Api(name, [Endpoint(api_name, href)])
    return apis


def parse_operations(site):
    body = site.find("body")
    operations = body.find("ul", "operations")
    operations = operations.find_all("li", "operation")
    return operations


def parse_apis(apis: dict[str, Api], path: str = "models", url: str = "https://developer.riotgames.com/apis",
               parser: str = "lxml", js_load_time: int = 3):
    session = HTMLSession()
    if not os.path.exists(path):
        os.mkdir(path)
    for name, api in apis.items():
        logger.info(f"current api: {name}")
        logger.debug(name, api)
        api_path = os.path.join(path, name)
        if not os.path.exists(api_path):
            os.mkdir(api_path)
        for endpoint in api.endpoints:
            logger.info(f"current endpoint: {endpoint.name}")
            logger.debug(endpoint)
            # get the side os the endpoint
            site = session.get(f'{url}{endpoint.href}')
            logger.debug(site)
            # render the site aka load the java-script, wait 3 sec to let it load
            site.html.render(sleep=js_load_time)
            # parse site with bs4
            site = BeautifulSoup(site.html.html, features=parser)
            for operation in parse_operations(site):
                logger.debug(operation.find("span", "path").text.strip())
                logger.info(f'current section of the site: {operation.find("span", "path").text.strip()}')
                content = operation.find("div", "api_block")
                schema = {'title': "ERROR"}
                definitions = False
                for response_block in content.find_all("div", "response_body"):
                    if raw_block := parse_block_response_body(response_block):
                        if not definitions:
                            schema.update(parse_response_block_to_schema(raw_block))
                            definitions = True
                        else:
                            definition = parse_response_block_to_definition(raw_block)
                            if n := schema.get('definitions'):
                                n.update(definition)
                            else:
                                schema['definitions'] = definition

                # save the json schema if exist
                if schema['title'] != "ERROR":
                    with open(os.path.join(api_path, f"{schema['title']}.json"), "w") as fp:
                        json.dump(schema, fp)

                # cleanup
                PARSED[:] = []
                del schema


def generate_python_code(out_path: str = "python", json_path: str = "models"):
    if not os.path.exists(out_path):
        os.mkdir(out_path)
    for directory in os.listdir(json_path):
        path = os.path.join(json_path, directory)
        output_dir = os.path.join(out_path, directory)
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)
        for file in os.listdir(path):
            file_path = Path(os.path.join(path, file))
            logger.debug(f"read json file from: {file_path}")
            output = Path(os.path.join(output_dir, f"{file.split('.')[0]}.py"))
            logger.debug(f"save generated python file to: {output}")
            generate(file_path, input_file_type=InputFileType.JsonSchema, input_filename=file, output=output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--parser', default='lxml', dest='parser', help='select a parser for bs4, default: lxml',
                        required=True)
    parser.add_argument('-jp', '--jsonpath', required=True, default='models',
                        help='Path to store the json schema file, default: models', dest='json_path')
    parser.add_argument('-pp', '--pythonpath', required=True, default='python',
                        help='Path to store the python file, default: python',
                        dest='python_path')
    parser.add_argument('-u', '--url', required=True, default='https://developer.riotgames.com/apis',
                        help='url to riot developers page with the api documentation, default: https://developer.riotgames.com/apis',
                        dest='url')
    args = parser.parse_args()

    api_endpoints = get_api_endpoints(args.url, args.parser)
    parse_apis(apis=api_endpoints, parser=args.parser, url=args.url, path=args.json_path)
    generate_python_code(out_path=args.python_path, json_path=args.json_path)
