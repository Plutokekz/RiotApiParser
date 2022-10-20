from pathlib import Path
from pprint import pprint

import requests
from black import List
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import json

from typing import Optional, Dict

from pydantic import BaseModel, Field
from datamodel_code_generator import InputFileType, generate

class Data(BaseModel):
    value: Optional[int]
    value1: Optional[str]

class AccountDto(BaseModel):
    puuid: Optional[str] = None
    gameName: Optional[str] = Field(
        None,
        description="This field may be excluded from the response if the account doesn't have a gameName.",
    )
    tagLine: Optional[str] = Field(
        None,
        description="This field may be excluded from the response if the account doesn't have a tagLine.",
    )
    test0: Dict[int, int] = Field(None, description="Map[String, String]")
    #test1: Dict[int, int] = Field(None, description="Map[String, String]")
    #test2: Dict[int, int] = Field(None, description="Map[String, String]")
    #test3: Dict[int, int] = Field(None, description="Map[String, String]")
    #test4: Dict[int, int] = Field(None, description="Map[String, String]")
    test1: List[Dict[str, List[Dict[int, List[str]]]]]

    data: Optional[Data]


pprint(AccountDto.schema())
with open("test_gen.json", 'w') as fp:
    json.dump(AccountDto.schema(), fp)
file_path = Path("test_gen.json")
output = Path("test_gen.py")
generate(file_path, input_file_type=InputFileType.JsonSchema, input_filename="test_gen.json", output=output)

exit()
template = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": None,
    "type": "object",
    "properties": {}
}


def parse_response_block(block):
    try:
        title = block.find("h5").text
    except AttributeError:
        return None
    title = title.strip()
    schema = template.copy()
    schema["title"] = title
    body = block.find("tbody")
    for row in body.find_all("tr"):
        name, type_, description = row.find_all("td")[:3]
        if description.text.strip():
            schema["properties"][name.text.strip()] = {"type": type_.text.strip(),
                                                       "description": description.text.strip()}
        else:
            schema["properties"][name.text.strip()] = {"type": type_.text.strip()}
    # print(schema)
    with open(f"{title}.json", "w") as fp:
        json.dump(schema, fp)


# create an HTML Session object
session = HTMLSession()

# Run JavaScript code on webpage


r = session.get('https://developer.riotgames.com/apis#account-v1')
x = r.html.render(sleep=2)
site = BeautifulSoup(r.html.html, features="lxml")
# nprint(site)
# body = r.html.find("body")
body = site.find("body")
# print(body)
page = body.find("div", "page")
operations = body.find("ul", "operations", recursive=True)
for operation in operations.find_all("li", "operation"):
    print(operation.find("span", "path").text)
    content = operation.find("div", "api_block")
    parse_response_block(content)
