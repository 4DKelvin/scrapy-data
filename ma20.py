import requests
import json
import cgi, base64
import datetime
import logging
import os.path
import threading
from time import ctime, sleep
from pprint import pprint
from pyquery import PyQuery


def get_stocks():
    response = requests.get('http://quote.eastmoney.com/stock_list.html')
    doc = PyQuery(response.content.decode('gbk'))

    arr = doc.find('.qox .quotebody ul li a')
    r1 = []
    r2 = []
    for i in arr:
        code = PyQuery(i).attr('href').replace('http://quote.eastmoney.com/', '').replace('.html', '')
        if code.find('sh') == 0:
            r1.append(code)
        else:
            r2.append(code)
    return r1, r2


def get_capital(code):
    try:
        response = requests.get('https://gupiao.baidu.com/stock/' + str(code) + '.html')
        doc = PyQuery(response.content)
        return int(float(doc.find('.stock-bets .line2 dl:last dd').text().replace('亿', '')) * 100000000)
    except:
        print('\033[1;34;40m[系统]\033[1;35;40m[' + str(code) + ']\033[0m获取流通股本失败...')
        return False


def get_detail(code):
    try:
        response = requests.get('https://gupiao.baidu.com/api/stocks/stockbasicinfo', params={
            "from": 'pc',
            "os_ver": 1,
            "cuid": 'xxx',
            "vv": 100,
            "format": 'json',
            "stock_code": code
        })
        return dict(json.loads(response.text))
    except:
        print('\033[1;34;40m[系统]\033[1;35;40m[' + str(code) + ']\033[1;31;40m获取行业类型失败...\033[0m')
        return False


def get_kline(stock, type):
    response = requests.get('https://gupiao.baidu.com/api/stocks/stock' + str(type) + 'bar', params={
        "from": 'pc',
        "os_ver": 1,
        "cuid": 'xxx',
        "vv": 100,
        "format": 'json',
        "stock_code": stock,
        "step": 3,
        "start": '',
        "count": 90,
        "fq_type": 'no'
    })
    res = dict(json.loads(response.text))
    if res.get('mashData'):
        res = res.get('mashData')
        res[0]['stock'] = {
            "code": stock,
            "type": type
        }
        # _ma(res, 30)
        # _ma(res, 60)
        # _ma(res, 90)
        return res
    return False


def _ma(res, count):
    for i in range(0, len(res) - count, 1):
        end = i + count - 1
        close = 0
        volume = 0
        for j in range(i, end + 1):
            close += res[j]['kline']['close']
            volume += res[j]['kline']['volume']
        res[i]['ma' + str(count)] = {
            "volume": volume / count,
            "avgPrice": close / count,
            "ccl": None
        }


def upper_line(data, source, target):
    now_diff = data[0][target]['avgPrice'] - data[0][source]['avgPrice']
    prev_diff = data[1][target]['avgPrice'] - data[1][source]['avgPrice']
    return prev_diff > now_diff >= 0


def vad_ma(res, history, kpi):
    if not res or len(res) <= 1 or res[0]['kline']['netChangeRatio'] == 'INF':
        return False
    data = {
        "validate": res[0]['kline']['low'] <= res[0]['ma' + str(kpi)]['avgPrice'] and res[0]['kline'][
                                                                                          'netChangeRatio'] < 0,
        "code": res[0]["stock"]["code"],
        "type": res[0]["stock"]["type"],
        "current": {
            "low": round(res[0]['kline']['low'], 2),
            "close": round(res[0]['kline']['close'], 2),
            "volume": res[0]['kline']['volume'] * 100,
            "ma" + str(kpi): round(res[0]['ma' + str(kpi)]['avgPrice'], 2),
            "line": {
                "ma5-10": upper_line(res, 'ma5', 'ma10'),
                "ma5-20": upper_line(res, 'ma5', 'ma20')
            }
        },
        "history": [],
        "kpi": "ma" + str(kpi),
        "range": history,
        "percent": False,
        "change": False
    }
    total_percent = 0
    total_change = 0
    count = 0
    for step in history:
        if step >= len(res):
            break
        match = 0
        tumble = 0
        rise = 0
        ratio = 0
        for i in range(1, step + 1, 1):
            if res[i]['kline']['low'] <= res[i]['ma' + str(kpi)]['avgPrice']:
                match += 1
                if res[i]['kline']['netChangeRatio'] < 0:
                    tumble += 1
                    if res[i - 1]['kline']['netChangeRatio'] > 0:
                        rise += 1
                        ratio += res[i - 1]['kline']['netChangeRatio']
        percent = rise / tumble if tumble > 0 and rise > 0 else False
        change = ratio / rise if ratio > 0 and rise > 0 else False
        data["history"].append({
            "range": step,
            "match": match,
            "tumble": tumble,
            "rise": rise,
            "change": change,
            "percent": percent
        })
        if percent:
            total_percent += percent
            total_change += change
            count += 1
    data["change"] = total_change / count if total_change > 0 and count > 0 else False
    data["percent"] = total_percent / count if total_percent > 0 and count > 0 else False
    return data


def worker(stocks):
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    for code in stocks:
        kline = get_kline(code, 'week')
        if kline:
            print('\033[1;34;40m[系统]\033[1;35;40m[' + str(code) + ']\033[0m正在分析...')
            result = vad_ma(kline, [4, 8, 16, 32, 48], '20')
            if result and result['validate'] \
                    and result['current']["ma20"] < 10 \
                    and result['percent'] > 0.85 \
                    and result['change'] < 10:
                print('\033[1;32;40m[成功]\033[1;35;40m[' + str(code) + ']\033[1;32;40m股票历史已匹配策略，正在写入硬盘...\033[0m')
                if not os.path.isdir('./res/' + date):
                    os.mkdir('./res/' + date + '/')
                capital = get_capital(code)
                info = get_detail(code)
                if capital:
                    result["current"]["capital"] = capital
                    result["current"]["turnover"] = result['current']['volume'] / result['current']['capital']
                if info:
                    result["industry"] = info['industry']
                    result["business"] = info['mainBusiness']
                t = open('./res/' + date + '/' + code + '.json', "w+")
                t.write(json.dumps(result))
                t.close()
            else:
                print('\033[1;31;40m[失败]\033[1;35;40m[' + str(code) + ']\033[0m股票历史数据不符合策略，已放弃...')
        else:
            print('\033[1;34;40m[系统]\033[1;35;40m[' + str(code) + ']\033[0m跳过分析，原因：历史数据不足够分析')


def __main__():
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    print('\033[1;34;40m[系统]\033[0m正在获取历史数据...')
    r1, r2 = get_stocks()
    for t in [threading.Thread(target=worker, args=(r1,)), threading.Thread(target=worker, args=(r2,))]:
        t.setDaemon(True)
        t.start()
    t.join()
    print('\033[1;34;40m[系统]\033[1;35;40m[' + date + ']\033[0m本周共检索\033[1;32;40m ' +
          str(len(os.listdir('./res/' + str(date)))) + ' \033[0m条符合策略的股票纪录')


__main__()
