import sys
sys.path.insert(0, 'practice03')
import tools_weather, json

result = tools_weather.fetch_weather_by_date('青城山', '04-10', raw_json=True)
weather_data = result['raw']['weather'][0]

print('=== Day 级别数据（网站可能使用的） ===')
print('最高温（day）:', weather_data.get('maxtempC'), '°C')
print('最低温（day）:', weather_data.get('mintempC'), '°C')
print()

print('=== Hourly 级别数据（我们目前使用的） ===')
temps = []
for h in weather_data.get('hourly', []):
    temp = h.get('tempC')
    if temp:
        temps.append(int(temp))
if temps:
    print('小时最高温:', max(temps), '°C')
    print('小时最低温:', min(temps), '°C')
print()

print('=== 我们目前返回给 LLM 的数据 ===')
print(json.dumps(result['forecast'], ensure_ascii=False, indent=2))
