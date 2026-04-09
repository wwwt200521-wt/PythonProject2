import sys

from tools_weather import fetch_weather


def main() -> None:
    city = "".join(sys.argv[1:]).strip() or "青城山"
    result = fetch_weather(city)
    print(result.get("text", ""))


if __name__ == "__main__":
    main()

