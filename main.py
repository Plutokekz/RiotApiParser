import os
from pprint import pprint
from typing import Optional, Dict, Any

import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import json
from collections import namedtuple
import logging
from datamodel_code_generator import InputFileType, generate
from pathlib import Path
import argparse
from lexer import Lexer, TokenType, Parser

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__file__)

RawProperty = namedtuple('RawProperty', ['name', 'type', 'description'])
RawBlock = namedtuple('RawBlock', ['name', 'raw_properties'])
Api = namedtuple("Api", ['name', 'endpoints'])
Endpoint = namedtuple('Endpoint', ['name', 'href'])
URL = "https://developer.riotgames.com/apis"
token_mapping = {
    'string': TokenType.STRING,
    'int': TokenType.INTEGER,
    'long': TokenType.LONG,
    'float': TokenType.FLOAT,
    'double': TokenType.DOUBLE,
    'boolean': TokenType.BOOLEAN,
    'list': TokenType.LIST,
    'map': TokenType.MAP
}
CONVERT = {
    TokenType.STRING: 'string',
    TokenType.INTEGER: 'integer',
    TokenType.LONG: 'integer',
    TokenType.FLOAT: 'number',
    TokenType.DOUBLE: 'number',
    TokenType.BOOLEAN: 'boolean'
}

lexer = Lexer(token_mapping)
parser = Parser(CONVERT)
# CONVERT = {
#    'string': 'string',
#    'int': 'integer',
#    'long': 'integer',
#    'float': 'number',
#    'double': 'number',
#    'boolean': 'boolean'
# }

PARSED = []
char_set = set()


class WebsiteParser:
    lexer: Lexer
    parser: Parser
    htmlparser: str

    def __init__(self, token_type_mapping, type_map, htmlparser: str):
        self.lexer = Lexer(token_type_mapping)
        self.parser = Parser(type_map)
        self.htmlparser = htmlparser

    def _parse_property(self, raw_property: RawProperty) -> Dict[str, Any]:
        # parse type
        token = list(self.lexer.lex_string(raw_property.type))
        property_ = self.parser.parse(token)
        # add description if exists
        if raw_property.description:
            property_['description'] = raw_property.description
        return {raw_property.name: property_}

    def _parse_block_response_body(self, block) -> Optional[RawBlock]:
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

    def _parse_response_block_to_definition(self, block: RawBlock) -> dict:
        # create dict definition dict with the name of the definition and an empty properties dict
        definition = {block.name: {"properties": {}}}
        for raw_property in block.raw_properties:
            # update the properties
            definition[block.name]["properties"].update(self._parse_property(raw_property))
        return definition

    def _parse_response_block_to_schema(self, block: RawBlock) -> Dict[str, Any]:
        schema = {"$schema": "http://json-schema.org/draft-07/schema#", "title": block.name, "type": "object",
                  "properties": {}}
        for raw_property in block.raw_properties:
            schema["properties"].update(self._parse_property(raw_property))
        return schema

    def _parse_operations(self, site: BeautifulSoup) -> Any:
        body = site.find("body")
        operations = body.find("ul", "operations")
        operations = operations.find_all("li", "operation")
        return operations

    def parse(self, site: str) -> Dict[str, Any]:
        site = BeautifulSoup(site.html.html, features=self.htmlparser)
        operation = self._parse_operations(site)
        content = operation.find("div", "api_block")
        schema = {'title': "ERROR"}
        definitions = False
        for response_block in content.find_all("div", "response_body"):
            if raw_block := self._parse_block_response_body(response_block):
                if not definitions:
                    schema.update(self._parse_response_block_to_schema(raw_block))
                    definitions = True
                else:
                    definition = self._parse_response_block_to_definition(raw_block)
                    if n := schema.get('definitions'):
                        n.update(definition)
                    else:
                        schema['definitions'] = definition

        # save the json schema if exist
        return schema


class ApiParser:

    def _parse_entry(self, entry) -> tuple[str, str, str]:
        m = entry.find('a')
        span = m.find("span")
        name = span.text.strip()
        api_name = m.get('api-name')
        href = m.get('href')
        name, api_name, href = name.strip(), api_name.strip(), href.strip()
        return name, api_name, href

    def _parse_entries(self, url: str, parser='lxml'):
        r = requests.get(url)
        site = BeautifulSoup(r.text, features=parser)
        match = site.find('div', class_="scrollable-container")
        match = match.find('ul')
        return match.find_all('li')

    def parse(self, url: str = "https://developer.riotgames.com/apis", parser: str = "lxml") -> dict[
        str, Api]:
        apis = {}
        for entry in self._parse_entries(url, parser):
            name, api_name, href = self._parse_entry(entry)
            if n := apis.get(name):
                n.endpoints.append(Endpoint(api_name, href))
            else:
                apis[name] = Api(name, [Endpoint(api_name, href)])
        return apis


def parse_apis(apis: dict[str, Api], path: str = "models",
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
            site = session.get(f'{URL}{endpoint.href}')
            logger.debug(site)
            # render the site aka load the java-script, wait 3 sec to let it load
            site.html.render(sleep=js_load_time)
            # parse site with bs4

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
            logger.info(f"parsing {file_path} to python")
            output = Path(os.path.join(output_dir, f"{file.split('.')[0]}.py"))
            logger.debug(f"save generated python file to: {output}")
            generate(file_path, input_file_type=InputFileType.JsonSchema, input_filename=file, output=output)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-p', '--parser', default='lxml', dest='parser',
                            help='select a parser for bs4, default: lxml')
    arg_parser.add_argument('-jp', '--jsonpath', default='models',
                            help='Path to store the json schema file, default: models', dest='json_path')
    arg_parser.add_argument('-pp', '--pythonpath', default='python',
                            help='Path to store the python file, default: python',
                            dest='python_path')
    arg_parser.add_argument('-u', '--url', default='https://developer.riotgames.com/apis',
                            help='url to riot developers page with the api documentation, default: https://developer.riotgames.com/apis',
                            dest='url')
    args = arg_parser.parse_args()

    endpoints_parser = ApiParser()
    api_endpoints = endpoints_parser.parse(args.url, args.parser)
    parse_apis(apis=api_endpoints, parser=args.parser, url=args.url, path=args.json_path)
    generate_python_code(out_path=args.python_path, json_path=args.json_path)
