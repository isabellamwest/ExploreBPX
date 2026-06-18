from bpx.parsers import parse_bpx_file

file = parse_bpx_file("example.json")

print(type(file))