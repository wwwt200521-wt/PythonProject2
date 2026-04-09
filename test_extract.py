import sys
sys.path.insert(0, 'practice03')
import tools_weather, json

result = tools_weather.fetch_weather_by_date('青城山', '04-10', raw_json=True)
print('=== 直接来自 _extract_forecast ===')
print(json.dumps(result['forecast'], ensure_ascii=False, indent=2))

weather_data = result['raw']['weather'][0]
print()
print('=== 原始日期数据 ===')
print('date:', weather_data.get('date'))
print('mintempC:', weather_data.get('mintempC'))
print('maxtempC:', weather_data.get('maxtempC'))
