from dash import html, set_props

class Logger:
    def __init__(self, component_id, property_name):
        self.component_id = component_id
        self.property_name = property_name
        self.__strings = []
        self.__print()

    def append(self, message):
        self.__strings.append(message)
        self.__print()

    def __print(self):
        html_strings = [html.P(s) for s in self.__strings]
        set_props(self.component_id, {self.property_name: html_strings})

