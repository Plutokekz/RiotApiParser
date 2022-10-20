import dataclasses
from enum import Enum
from pprint import pprint
from typing import List, Dict, Generator, Any
import string


class TokenType(Enum):
    STRING = 0
    INTEGER = 1
    LONG = 2
    FLOAT = 3
    DOUBLE = 4
    BOOLEAN = 5
    LIST = 11
    MAP = 12
    CUSTOM = 6
    EOF = 7
    LPARREN = 8
    RPARREN = 9
    UNKNOWN = 10


@dataclasses.dataclass
class Token:
    type: TokenType
    value: str
    position: int


class UnknownCharacterException(Exception):
    """
    :raise: if the given Character is unknown
    """


class Lexer:
    string: str
    curser: int
    current_char: str
    token_type_mapping: Dict[str, TokenType]

    def __init__(self, token_type_mapping: Dict[str, TokenType]):
        self.token_type_mapping = token_type_mapping

    def lex_string(self, string_: str) -> Generator[Token, None, None]:
        self.string = string_
        self.curser = 0
        self.current_char = self.string[self.curser]
        while (token := self._get_next_token()).type != TokenType.EOF:
            yield token

    def _get_next_char(self) -> None:
        if self.curser + 1 < len(self.string):
            self.curser += 1
            self.current_char = self.string[self.curser]
        else:
            self.current_char = "\0"

    def _get_next_string(self) -> str:
        string_token = ""
        while True:
            string_token += self.current_char
            self._get_next_char()
            if self.current_char not in string.ascii_letters:
                break
        return string_token

    def _get_next_token(self) -> Token:
        while self.current_char in string.whitespace or self.current_char == ",":
            self._get_next_char()
        if self.current_char == "\0":
            token = Token(position=self.curser, type=TokenType.EOF, value=self.current_char)
            self._get_next_char()
            return token
        if self.current_char == "[":
            token = Token(position=self.curser, type=TokenType.LPARREN, value=self.current_char)
            self._get_next_char()
            return token
        if self.current_char == "]":
            token = Token(position=self.curser, type=TokenType.RPARREN, value=self.current_char)
            self._get_next_char()
            return token
        if self.current_char.isalpha():
            token_string = self._get_next_string()
            token_type = self.token_type_mapping.get(token_string.lower(), TokenType.CUSTOM)
            token = Token(type=token_type, value=token_string, position=self.curser)
            self._get_next_char()
            return token
        else:
            raise UnknownCharacterException(
                f"Position {self.curser}, Character <{self.current_char}>, String {self.string}")


CONVERT = {
    TokenType.STRING: 'string',
    TokenType.INTEGER: 'integer',
    TokenType.LONG: 'integer',
    TokenType.FLOAT: 'number',
    TokenType.DOUBLE: 'number',
    TokenType.BOOLEAN: 'boolean'
}


class Parser:
    type_map: Dict[TokenType, str]
    tokens: List[Token]
    current_token: Token
    curser: int

    def __init__(self, type_map: Dict[TokenType, str]):
        self.type_map = type_map

    def _advance(self) -> None:
        self.curser += 1
        if self.curser < len(self.tokens):
            self.current_token = self.tokens[self.curser]

    def parse(self, tokens: List[Token]) -> Dict[str, Any]:
        self.tokens = tokens
        self.curser = -1
        self._advance()
        return self.type()

    def array(self) -> Dict[str, Any]:
        self._advance()
        return {"type": "array",
                "items": self.type()}

    def map(self) -> Dict[str, Any]:
        self._advance()
        return {"type": "object",
                "additionalProperties": self.type()}

    def custom(self) -> Dict[str, str]:
        return {"$ref": f"#/definitions/{self.current_token.value}"}

    def type(self) -> Dict[str, Any]:
        if self.current_token.type == TokenType.LIST:
            return self.array()
        if self.current_token.type == TokenType.MAP:
            return self.map()
        if self.current_token.type == TokenType.CUSTOM:
            return self.custom()
        return {"type": self.type_map.get(self.current_token.type)}


if __name__ == "__main__":
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
    lexer = Lexer(token_mapping)
    tokens = lexer.lex_string("Map[String, Map[String, string]]")
    parser = Parser(CONVERT)
    pprint(parser.parse(list(tokens)))
