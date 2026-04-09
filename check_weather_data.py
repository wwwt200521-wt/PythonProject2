import sys
sys.path.insert(0, 'practice03')
import tools_weather, json

result = tools_weather.fetch_weather_by_date('青城山', '04-10', raw_json=True)
weather_data = result['raw']['weather'][0] if result['raw'].get('weather') else {}

print('=== 原始API JSON数据（每次请求都是实时的，不是写死的）===')
print('日期:', weather_data.get('date'))
print('最高温:', weather_data.get('maxtempC'), '°C')
print('最低温:', weather_data.get('mintempC'), '°C')
print('平均温:', weather_data.get('avgtempC'), '°C')
print()
print('小时数据（样本）:')
hourly_list = weather_data.get('hourly', [])
for h in hourly_list[:5]:
    print(f"  时间 {h.get('time')}: {h.get('tempC')}°C")
