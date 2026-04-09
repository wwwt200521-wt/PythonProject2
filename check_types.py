import sys
sys.path.insert(0, 'practice03')
import tools_weather, json

result = tools_weather.fetch_weather_by_date('青城山', '04-10', raw_json=True)
weather_data = result['raw']['weather'][0]

print('Raw day data:')
print('mintempC type:', type(weather_data.get('mintempC')), '| value:', repr(weather_data.get('mintempC')))
print('maxtempC type:', type(weather_data.get('maxtempC')), '| value:', repr(weather_data.get('maxtempC')))
print('avgtempC type:', type(weather_data.get('avgtempC')), '| value:', repr(weather_data.get('avgtempC')))
