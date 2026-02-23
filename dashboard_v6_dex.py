import sys, os, time, requests, datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from gtts import gTTS

# --- 설정 ---
SERVICE_KEY = "api키" #api키입력 
NX, NY = 50, 100 #좌표값 입력
STATION_NAME = "송파" #미세먼지 위치값
BRIEFING_PATH = "/home/pi/javis_dashboard/latest_briefing.txt"
SCREENSAVER_TIME = 120 
THEME = os.getenv("DASHBOARD_THEME", "cyberpunk")

class WeatherThread(QThread):
    weather_data_ready = pyqtSignal(dict)
    def run(self):
        safe_key = urllib.parse.unquote(SERVICE_KEY)
        while True:
            data = {'cur_temp': '--', 'cur_humi': '--', 'cur_wind': '0', 'cur_vec': '--', 'pm10': '-', 'pm25': '-', 'briefing': "", 'status': 'success', 'feels': '--', 'fcst_temp': '--', 'fcst_sky': '1'}
            try:
                now = datetime.datetime.now()
                b_date, b_time = (now if now.minute >= 50 else now - datetime.timedelta(hours=1)).strftime("%Y%m%d"), (now if now.minute >= 50 else now - datetime.timedelta(hours=1)).strftime("%H00")
                
                # 1. 날씨 실황
                w_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"
                w_res = requests.get(w_url, params={'serviceKey': safe_key, 'dataType': 'JSON', 'base_date': b_date, 'base_time': b_time, 'nx': NX, 'ny': NY}, timeout=5).json()
                if 'item' in str(w_res):
                    ncst = {i['category']: i['obsrValue'] for i in w_res['response']['body']['items']['item']}
                    data.update({'cur_temp': ncst.get('T1H', '--'), 'cur_humi': ncst.get('REH', '--'), 'cur_wind': ncst.get('WSD', '0')})
                    vec = int(ncst.get('VEC', 0))
                    data['cur_vec'] = ["북", "북동", "동", "남동", "남", "남서", "서", "북서", "북"][int((vec + 22.5) / 45)]
                    if data['cur_temp'] != '--':
                        t, w = float(data['cur_temp']), float(data['cur_wind'])
                        data['feels'] = str(round(13.12 + 0.6215*t - 11.37*(w**0.16) + 0.3965*t*(w**0.16), 1))

                # 2. 미세먼지
                d_url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
                d_res = requests.get(d_url, params={'serviceKey': safe_key, 'returnType': 'json', 'stationName': STATION_NAME, 'dataTerm': 'DAILY', 'ver': '1.0'}, timeout=5).json()
                if 'items' in str(d_res):
                    item = d_res['response']['body']['items'][0]
                    data.update({'pm10': item.get('pm10Value', '-'), 'pm25': item.get('pm25Value', '-')})

                if os.path.exists(BRIEFING_PATH):
                    with open(BRIEFING_PATH, 'r', encoding='utf-8') as f:
                        data['briefing'] = f.read().strip() + "\n\n" + " " * 50 + " ◎ JAVIS OS ONLINE "

                self.weather_data_ready.emit(data)
            except: pass
            time.sleep(1800)

class JavisDashboard(QWidget):
    
    def __init__(self):
        super().__init__()
        self.last_activity = time.time()
        self.is_screensaver = False
        self.radio_playing = False
        
        # 오디오 초기화 (FFmpeg 경고 완화 및 정상 출력용)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.8) # 볼륨 80%
        
        self.initUI()
        
        # 타이머들
        self.timer = QTimer(self); self.timer.timeout.connect(self.update_tick); self.timer.start(1000)
        self.scroll_timer = QTimer(self); self.scroll_timer.timeout.connect(self.auto_scroll); self.scroll_timer.start(40)
        
        # 브리핑 파일 감시 타이머 (파일이 바뀌면 즉시 반영)
        self.file_timer = QTimer(self); self.file_timer.timeout.connect(self.load_briefing); self.file_timer.start(5000)
        self.load_briefing()
        
        
        # 날씨 업데이트 스레드는 기존 로직을 유지한다고 가정합니다.
        # 아래는 UI 구성 및 요청하신 특수 로직 위주입니다.

    def initUI(self):
        # 800*480 전체화면 및 상단바 제거
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(800, 480); self.showFullScreen(); self.setCursor(Qt.CursorShape.BlankCursor)
        self.setStyleSheet("background-color: #0D0D0D; color: #00FFFF; font-family: 'NanumBarunGothic';")

        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(10, 10, 10, 10); self.main_layout.setSpacing(0)

        # --- [상단 존: 일반모드용] ---
        self.top_widget = QWidget(); self.top_widget.setFixedHeight(300)
        top_h = QHBoxLayout(self.top_widget)

        # 1. 왼쪽: 현재날씨 (160px)
        self.weather_zone = QFrame(); self.weather_zone.setFixedWidth(160)
        w_v = QVBoxLayout(self.weather_zone)
        self.w_icon = QLabel("☀️"); self.w_icon.setStyleSheet("font-size: 55px;")
        self.w_temp = QLabel("--°C"); self.w_temp.setStyleSheet("font-size: 38px; font-weight: bold;")
        self.w_feels = QLabel("체감 --°C"); self.w_feels.setStyleSheet("font-size: 14px; color: #BBBBBB;")
        self.w_wind_humi = QLabel("🚩 --m/s | 💧 --%"); self.w_wind_humi.setStyleSheet("font-size: 14px;")
        for w in [self.w_icon, self.w_temp, self.w_feels, self.w_wind_humi]: w_v.addWidget(w, alignment=Qt.AlignmentFlag.AlignCenter)

        # 2. 가운데: 시계/날짜/옷차림 (440px)
        self.clock_zone = QFrame(); self.clock_zone.setFixedWidth(440)
        c_v = QVBoxLayout(self.clock_zone)
        self.clock_label = QLabel("00:00"); self.clock_label.setStyleSheet("font-size: 110px; font-weight: bold;")
        self.date_label = QLabel("DATE"); self.date_label.setStyleSheet("font-size: 20px;")
        self.cloth_label = QLabel("💡 분석 중..."); self.cloth_label.setStyleSheet("font-size: 16px; color: #FF00FF;")
        c_v.addStretch(); c_v.addWidget(self.clock_label, alignment=Qt.AlignmentFlag.AlignCenter)
        c_v.addWidget(self.date_label, alignment=Qt.AlignmentFlag.AlignCenter)
        c_v.addWidget(self.cloth_label, alignment=Qt.AlignmentFlag.AlignCenter); c_v.addStretch()

        # 3. 오른쪽: 미세먼지/예보 (160px)
        self.dust_zone = QFrame(); self.dust_zone.setFixedWidth(160)
        d_v = QVBoxLayout(self.dust_zone)
        self.pm10_label = QLabel("미세: -"); self.pm25_label = QLabel("초미세: -")
        self.fcst_1 = QLabel("오후 --°C"); self.fcst_2 = QLabel("내일 --°C")
        for d in [self.pm10_label, self.pm25_label, self.fcst_1, self.fcst_2]: d_v.addWidget(d, alignment=Qt.AlignmentFlag.AlignCenter)

        top_h.addWidget(self.weather_zone); top_h.addWidget(self.clock_zone); top_h.addWidget(self.dust_zone)

        # --- [구분 바] ---
        self.line = QFrame(); self.line.setFrameShape(QFrame.Shape.HLine); self.line.setStyleSheet("background-color: #FF00FF; min-height: 2px;")

        # --- [하단 존: 브리핑 & 화면보호기 날씨] ---
        # 하단 스택 위젯 설정 부분 수정
        self.bottom_stack = QStackedWidget()
        self.bottom_stack.setFixedHeight(150)
        
        # 일반모드: 브리핑 스크롤
        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(True); self.scroll_area.setStyleSheet("border: none; background: transparent;")
        self.briefing_label = QLabel("JAVIS OS ONLINE..."); self.briefing_label.setWordWrap(True)
        self.briefing_label.setStyleSheet("font-size: 18px; line-height: 1.8; color: #EEEEEE;")
        self.scroll_area.setWidget(self.briefing_label); self.scroll_area.verticalScrollBar().hide()
        
        # 화면보호기모드: 가로 날씨 정보
        self.ss_weather_widget = QWidget()
        ss_h = QHBoxLayout(self.ss_weather_widget)
        self.ss_info_label = QLabel("--°C | 습도 --% | 미세 --")
        self.ss_info_label.setStyleSheet("font-size: 35px; font-weight: bold; color: #00FFFF;")
        ss_h.addWidget(self.ss_info_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.bottom_stack.addWidget(self.scroll_area) # Index 0
        self.bottom_stack.addWidget(self.ss_weather_widget) # Index 1

        self.main_layout.addWidget(self.top_widget)
        self.main_layout.addWidget(self.line) # 일반모드에서만 보임
        self.main_layout.addWidget(self.bottom_stack)
        

    def create_flip_label(self, w, h, fs):
        l = QLabel("00"); l.setAlignment(Qt.AlignmentFlag.AlignCenter); l.setFixedSize(w, h)
        l.setStyleSheet(f"background: #2a2a2a; color: {self.accent}; font-size: {fs}px; font-weight: bold; border-radius: 10px;")
        return l

    def update_weather_ui(self, data):
        try:
            # 1. 왼쪽: 현재 날씨
            self.w_temp.setText(f"{data['cur_temp']}°C")
            self.w_humi.setText(f"💧 {data['cur_humi']}%")
            self.w_feels.setText(f"체감 {data.get('feels','--')}°C")
            self.w_wind.setText(f"🚩 {data['cur_vec']} {data['cur_wind']}m/s")
             
            
            # 2. 오른쪽: 미세먼지 수치별 색상 적용 (주인님 가이드 반영)
            pm10 = int(data['pm10']) if str(data['pm10']).isdigit() else 0
            pm25 = int(data['pm25']) if str(data['pm25']).isdigit() else 0
            
            # 미세먼지 색상 로직
            p10_c = "#0000FF" if pm10 <= 30 else "#00FF00" if pm10 <= 80 else "#FF8000" if pm10 <= 150 else "#FF0000"
            # 초미세먼지 색상 로직
            p25_c = "#0000FF" if pm25 <= 15 else "#00FF00" if pm25 <= 35 else "#FF8000" if pm25 <= 75 else "#FF0000"
            
            self.pm10_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {p10_c};")
            self.pm10_label.setText(f"😷 미세: {pm10}")
            self.pm25_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {p25_c};")
            self.pm25_label.setText(f"😷 초미세: {pm25}")

            # 3. 옷차림 추천 로직 (기온 기반)
            temp_float = float(data['cur_temp']) if data['cur_temp'] != '--' else 20
            self.cloth_label.setText(f"💡 {self.get_clothing_recommendation(temp_float)}")

            # 4. 하단 브리핑 로드 (파일 읽기 강화)
            if os.path.exists(BRIEFING_PATH):
                with open(BRIEFING_PATH, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        self.briefing_label.setText(content)
            
            # 5. 예보 (오전/오후 분기)
            is_morning = datetime.datetime.now().hour < 12
            self.fcst_1.setText(f"오후 ⛅ {data.get('fcst_temp', '--')}°C" if is_morning else f"내일 오전 ☀️ {data.get('fcst_temp', '--')}°C")
            
            # 화면보호기용 텍스트 업데이트
            ss_text = f"{data['cur_temp']}°C | 💧 {data['cur_humi']}% | 😷 미세 {data['pm10']}"
            self.ss_info_label.setText(ss_text)
            
        except Exception as e:
            print(f"Update Error: {e}")
            
    def get_clothing_recommendation(self, temp):
        if temp >= 28: return "민소매, 반바지, 린넨 옷"
        if temp >= 23: return "반팔, 얇은 셔츠, 반바지"
        if temp >= 20: return "긴팔티, 가디건, 면바지"
        if temp >= 17: return "니트, 맨투맨, 청바지"
        if temp >= 12: return "자켓, 가디건, 야상"
        if temp >= 9: return "트렌치코트, 야상, 기모바지"
        if temp >= 5: return "코트, 가죽자켓, 히트텍"
        return "패딩, 두꺼운 코트, 목도리"
        
    # --- 기능 로직 ---
    def load_briefing(self):
        """파일에서 브리핑 내용을 읽어 레이블에 세팅"""
        if os.path.exists(BRIEFING_PATH):
            try:
                with open(BRIEFING_PATH, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content and self.briefing_label.text() != content:
                        self.briefing_label.setText(content)
                        self.briefing_label.adjustSize()
            except: pass
            
    # --- 스크롤 로직 (무한 루프) ---
    def auto_scroll(self):
        if self.is_screensaver: return
        bar = self.scroll_area.verticalScrollBar()
        if bar.value() >= bar.maximum():
            if not self.briefing_label.text().endswith("*****"):
                self.briefing_label.setText(self.briefing_label.text() + "\n\n*****")
            QTimer.singleShot(2000, lambda: bar.setValue(0))
        else:
            bar.setValue(bar.value() + 1)
            
            
    # --- 더블 탭 이벤트 처리 ---
    def mouseDoubleClickEvent(self, event):
        pos = event.pos()
        # 1. 날씨존 상단: 종료
        if self.weather_zone.geometry().contains(pos) and pos.y() < 150:
            QApplication.quit()
        # 2. 시계존: 라디오
        elif self.clock_zone.geometry().contains(pos):
            self.toggle_radio()
        # 3. 브리핑존: TTS
        elif self.bottom_scroll.geometry().contains(pos):
            self.play_tts(self.briefing_label.text().replace("*****", ""))

    def toggle_radio(self):
        if self.radio_playing:
            self.player.stop(); self.radio_playing = False
        else:
            now = datetime.datetime.now()
            day, hour, minute = now.weekday(), now.hour, now.minute
            # 라디오 스케줄링 로직
            url = "http://serpent0.duckdns.org:8088/mbcfm.pls"
            if (day == 4 and (7 <= hour < 8 or (hour == 8 and minute < 30))) or (day != 4 and 7 <= hour < 9):
                url = "http://serpent0.duckdns.org:8088/sbsfm.pls"
            self.player.setSource(QUrl(url)); self.player.play(); self.radio_playing = True

    def update_tick(self):
        now = QDateTime.currentDateTime()
        self.clock_label.setText(now.toString("HH:mm"))
        self.date_label.setText(now.toString("yyyy. MM. dd. ddd요일"))
        
        # 3분 무활동 체크
        if time.time() - self.last_activity > SCREENSAVER_TIME and not self.is_screensaver:
            self.set_screensaver(True)

    def set_screensaver(self, active):
        self.is_screensaver = active
        if active:
            self.top_widget.hide()
            self.line.hide() # 화면보호기에서 가로바 제거 요청 반영
            self.bottom_stack.setCurrentIndex(1)
            # 화면보호기 전용 거대 시계 위젯 배치 (전체화면급)
            self.show_giant_clock(True) 
        else:
            self.last_activity = time.time()
            self.top_widget.show()
            self.line.show()
            self.bottom_stack.setCurrentIndex(0)
            self.show_giant_clock(False)

    def mouseDoubleClickEvent(self, event):
        pos = event.pos()
        if self.weather_zone.geometry().contains(pos) and pos.y() < 150: QApplication.quit()
        elif self.clock_zone.geometry().contains(pos): self.toggle_radio()
        elif self.bottom_stack.geometry().contains(pos): 
            self.play_tts(self.briefing_label.text().replace("*****", ""))

    def play_tts(self, text):
        # TTS 실행 시 메인 스레드가 멈추지 않도록 처리
        try:
            tts = gTTS(text=text, lang='ko')
            tts_file = "briefing.mp3"
            tts.save(tts_file)
            self.player.setSource(QUrl.fromLocalFile(os.path.abspath(tts_file)))
            self.player.play() 
            # 재생 시작 후 바로 리턴하여 스크롤이 멈추지 않게 함
        except Exception as e:
            print(f"TTS Error: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dashboard = JavisDashboard(); dashboard.show()
    sys.exit(app.exec())
