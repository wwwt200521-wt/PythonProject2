import sys
sys.path.insert(0, 'practice03')
import tools_weather, json

result = tools_weather.fetch_weather_by_date('青城山', '04-10', raw_json=True)
weather_list = result['raw'].get('weather', [])

print('=== wttr.in 返回的所有天气日期 ===')
for i, day in enumerate(weather_list):
    print(f'[{i}] date: {day.get("date")}, min: {day.get("mintempC")}, max: {day.get("maxtempC")}')
