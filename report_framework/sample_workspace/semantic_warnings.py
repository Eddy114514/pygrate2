from io import BytesIO
import base64


mapping = {"a": 1, "b": 2}
second_key = mapping.keys()[1]
second_value = mapping.values()[1]
second_item = mapping.items()[1]

for number in range(3):
    pass

numbers = list(range(3)) + [4]

base64_text = "prefix:" + base64.b64encode("x")
base32_text = "prefix:" + base64.b32encode("x")
base16_text = "prefix:" + base64.b16encode("x")

base64_text = "prefix:" + base64.b64encode("x")
base32_text = "prefix:" + base64.b32encode("x")
base16_text = "prefix:" + base64.b16encode("x")

stream = BytesIO("AAAA")
stream.seek(2)
stream.truncate(0)
