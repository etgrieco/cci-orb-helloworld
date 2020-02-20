import requests

def main():
    print('hello world')

    res = requests.get('http://www.example.com')

    print(res.content)

main()
