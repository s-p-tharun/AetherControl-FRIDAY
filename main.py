import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import time
import math
import pyttsx3
import threading
import queue

try:
    import screen_brightness_control as sbc

    SBC_AVAILABLE = True
except ImportError:
    print("WARNING: 'screen-brightness-control' module not found.")
    SBC_AVAILABLE = False

# --- CONFIGURATION ---
SMOOTHING = 4.0
READ_SCROLL_SPEED = 150

# --- VOICE ENGINE (SOFT FEMININE VOICE) ---
tts_queue = queue.Queue()


def tts_worker():
    """Background thread to process speech without lagging the video feed."""
    engine = pyttsx3.init()

    voices = engine.getProperty('voices')
    target_voice = None

    for voice in voices:
        name = voice.name.lower()
        if 'zira' in name or 'hazel' in name or 'samantha' in name or 'female' in name:
            target_voice = voice.id
            break

    if target_voice:
        engine.setProperty('voice', target_voice)

    engine.setProperty('rate', 165)
    engine.setProperty('volume', 0.9)

    while True:
        text = tts_queue.get()
        if text is None: break
        engine.say(text)
        engine.runAndWait()
        tts_queue.task_done()


threading.Thread(target=tts_worker, daemon=True).start()


def speak(text):
    tts_queue.put(text)


speak("Hello Boss. Systems initialized.")

# --- INITIALIZE MEDIAPIPE ---
mp_hands = mp.solutions.hands
mp_face_mesh = mp.solutions.face_mesh
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.8, min_tracking_confidence=0.8)
face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, min_detection_confidence=0.7)

cap = cv2.VideoCapture(0)
screen_w, screen_h = pyautogui.size()
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0


# --- STATE MANAGEMENT ---
class SystemState:
    def __init__(self):
        self.cursor_x, self.cursor_y = screen_w / 2, screen_h / 2

        # Click Arming States
        self.l_click_armed = False
        self.r_click_armed = False
        self.is_dragging = False

        self.last_vol_time = 0.0
        self.last_bright_time = 0.0

        # Mode Toggles
        self.game_mode_active = False
        self.game_toggle_start_time = 0.0
        self.game_action_triggered = False
        self.game_exit_start_time = 0.0

        self.read_mode_active = False
        self.read_toggle_start_time = 0.0
        self.read_action_triggered = False
        self.last_scroll_time = 0.0

        # Cooldowns & Timers
        self.last_pinky_nav_time = 0.0
        self.pinky_clicked = False
        self.last_action_time = 0.0

        # HUD Data
        self.ui_meter_type = "NONE"
        self.ui_meter_val = 0.5


state = SystemState()


def get_finger_states(lms):
    index_up = lms[8].y < lms[6].y
    middle_up = lms[12].y < lms[10].y
    ring_up = lms[16].y < lms[14].y
    pinky_up = lms[20].y < lms[18].y
    thumb_open = math.hypot(lms[4].x - lms[9].x, lms[4].y - lms[9].y) > 0.15
    states = [thumb_open, index_up, middle_up, ring_up, pinky_up]
    return states, sum(states)


def draw_cinematic_hud(frame, face_res, hand_res, mode, hold_display_text):
    """Highly vibrant, glowing sci-fi HUD"""
    h, w, _ = frame.shape

    # Darken background slightly to make neon pop
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (10, 15, 20), -1)
    frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

    hud_layer = np.zeros_like(frame)

    # Theme Colors (BGR)
    neon_cyan = (255, 255, 0)
    neon_orange = (0, 150, 255)
    neon_pink = (255, 50, 200)
    neon_red = (0, 0, 255)

    color = neon_cyan
    if "GAME" in mode: color = neon_orange
    if "PAUSED" in mode:
        color = neon_red
    elif "READ" in mode:
        color = neon_pink
    elif "DRAG" in mode or "VOL" in mode or "BRIGHT" in mode:
        color = (0, 255, 0)

    # --- Draw Base UI Elements ---
    cv2.line(hud_layer, (40, 40), (120, 40), color, 2)
    cv2.line(hud_layer, (40, 40), (40, 120), color, 2)
    cv2.line(hud_layer, (w - 40, h - 40), (w - 120, h - 40), color, 2)
    cv2.line(hud_layer, (w - 40, h - 40), (w - 40, h - 120), color, 2)

    # Telemetry Text
    cv2.putText(hud_layer, f"SYS OP: {mode}", (50, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    if hold_display_text:
        cv2.putText(hud_layer, hold_display_text, (w - 400, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, neon_red, 2)

    # Dynamic Meter for Volume / Brightness
    if state.ui_meter_type != "NONE":
        meter_y = h - 60
        meter_w = 300
        meter_x = int((w / 2) - (meter_w / 2))

        cv2.putText(hud_layer, f"{state.ui_meter_type} LEVEL", (meter_x, meter_y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    color, 1)
        cv2.rectangle(hud_layer, (meter_x, meter_y), (meter_x + meter_w, meter_y + 10), (50, 50, 50), -1)
        fill_w = int(max(0, min(1.0, state.ui_meter_val)) * meter_w)
        cv2.rectangle(hud_layer, (meter_x, meter_y), (meter_x + fill_w, meter_y + 10), color, -1)

    # Center Reticle
    cx, cy = w // 2, h // 2
    cv2.circle(hud_layer, (cx, cy), 150, (30, 40, 50), 1)
    cv2.line(hud_layer, (cx, cy - 20), (cx, cy + 20), (50, 60, 70), 1)
    cv2.line(hud_layer, (cx - 20, cy), (cx + 20, cy), (50, 60, 70), 1)

    # --- CINEMATIC JARVIS VISOR OVERLAY ---
    if face_res.multi_face_landmarks:
        face = face_res.multi_face_landmarks[0]

        # Absolute focal tracking center (Nose point)
        nx, ny = int(face.landmark[1].x * w), int(face.landmark[1].y * h)

        # Determine dynamic boundaries based on extreme face coordinates
        x_coords = [lm.x for lm in face.landmark]
        y_coords = [lm.y for lm in face.landmark]
        fx1, fx2 = int(min(x_coords) * w), int(max(x_coords) * w)
        fy1, fy2 = int(min(y_coords) * h), int(max(y_coords) * h)

        face_width = fx2 - fx1
        face_height = fy2 - fy1

        # Visor parameters extending outward from face bounds
        pad_x = int(face_width * 0.4)
        pad_y = int(face_height * 0.2)
        vx1, vx2 = fx1 - pad_x, fx2 + pad_x
        vy1, vy2 = fy1 - pad_y, fy2 + pad_y

        # 1. Clean Convergence Vectors (X-Crossing through the Nose Tracking Point)
        cv2.line(hud_layer, (vx1, vy1), (vx2, vy2), color, 1)
        cv2.line(hud_layer, (vx1, vy2), (vx2, vy1), color, 1)

        # 2. Bold Glowing Focal Target Ring on Nose
        cv2.circle(hud_layer, (nx, ny), 22, color, 4, lineType=cv2.LINE_AA)
        cv2.circle(hud_layer, (nx, ny), 26, (255, 255, 255), 1, lineType=cv2.LINE_AA)

        # 3. Outer Curved Cinematic Visor Bracket Frame
        # Left Bracket Wing
        pts_left = np.array([[vx1 + 40, vy1], [vx1, vy1 + 30], [vx1, vy2 - 30], [vx1 + 40, vy2]], np.int32)
        cv2.polylines(hud_layer, [pts_left], False, color, 2, lineType=cv2.LINE_AA)

        # Right Bracket Wing
        pts_right = np.array([[vx2 - 40, vy1], [vx2, vy1 + 30], [vx2, vy2 - 30], [vx2 - 40, vy2]], np.int32)
        cv2.polylines(hud_layer, [pts_right], False, color, 2, lineType=cv2.LINE_AA)

        # 4. Minimalist Interface HUD Text Output
        cv2.putText(hud_layer, "TGT LOCK: ACTIVATED", (vx1 + 10, vy1 - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
                    lineType=cv2.LINE_AA)
        cv2.putText(hud_layer, "FACIAL MESH SCAN: ACTIVE", (vx1 + 10, vy1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color,
                    1, lineType=cv2.LINE_AA)

    # Draw Hand Details
    if hand_res.multi_hand_landmarks:
        for hand in hand_res.multi_hand_landmarks:
            mp_drawing.draw_landmarks(
                hud_layer, hand, mp_hands.HAND_CONNECTIONS,
                mp_drawing_styles.DrawingSpec(color=color, thickness=2, circle_radius=3),
                mp_drawing_styles.DrawingSpec(color=(255, 255, 255), thickness=1)
            )
            hx, hy = int(hand.landmark[9].x * w), int(hand.landmark[9].y * h)
            cv2.circle(hud_layer, (hx, hy), 20, color, 1)

    # Apply Glow
    glow = cv2.GaussianBlur(hud_layer, (15, 15), 0)
    frame = cv2.add(frame, glow)
    frame = cv2.add(frame, hud_layer)

    return frame


while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    hand_res = hands.process(rgb_frame)
    face_res = face_mesh.process(rgb_frame)

    current_mode = "IDLE"
    pause_cursor = True
    hold_display_text = ""
    state.ui_meter_type = "NONE"

    num_hands = 0
    if hand_res.multi_hand_landmarks:
        num_hands = len(hand_res.multi_hand_landmarks)

    # --- MODE TOGGLES ---
    if num_hands == 1:
        lms = hand_res.multi_hand_landmarks[0].landmark
        states, open_count = get_finger_states(lms)
        thumb_open, index_up, middle_up, ring_up, pinky_up = states

        # Index and Pinky Only (Spider-Man)
        is_spiderman = index_up and pinky_up and not middle_up and not ring_up and not thumb_open

        # Thumb, Index, Pinky
        is_game_toggle = thumb_open and index_up and not middle_up and not ring_up and pinky_up

        # Temporal Toggle: Read/Game Mode
        if is_spiderman and not state.game_mode_active:
            if state.read_toggle_start_time == 0.0: state.read_toggle_start_time = time.time()
            hold_dur = time.time() - state.read_toggle_start_time

            if not state.read_action_triggered:
                # Dynamic visual text based on current state
                if state.read_mode_active:
                    hold_display_text = f"EXITING READ/GAME MODE: {hold_dur:.1f}s"
                    current_mode = "READ/GAME: PAUSED (HOLD TO EXIT)"
                else:
                    hold_display_text = f"ACTIVATING READ/GAME MODE: {hold_dur:.1f}s"

                if hold_dur >= 3.0:
                    state.read_mode_active = not state.read_mode_active
                    state.read_action_triggered = True
                    # Voice triggers
                    if state.read_mode_active:
                        speak("Read mode. Activated.")
                    else:
                        speak("Read Mode. Deactivated.")
        else:
            state.read_toggle_start_time = 0.0
            state.read_action_triggered = False

        # Temporal Toggle: Game Mode
        if is_game_toggle and not state.read_mode_active:
            if state.game_toggle_start_time == 0.0: state.game_toggle_start_time = time.time()
            hold_dur = time.time() - state.game_toggle_start_time

            if not state.game_action_triggered:
                # Dynamic visual text based on current state
                if state.game_mode_active:
                    hold_display_text = f"EXITING GAME MODE: {hold_dur:.1f}s"
                else:
                    hold_display_text = f"ACTIVATING GAME MODE: {hold_dur:.1f}s"

                if hold_dur >= 3.0:
                    state.game_mode_active = not state.game_mode_active
                    state.game_action_triggered = True
                    # Voice triggers
                    if state.game_mode_active:
                        speak("GAME MODE ACTIVATED BOSS")
                    else:
                        speak("GAME MODE DEACTIVATED BOSS")
        else:
            state.game_toggle_start_time = 0.0
            state.game_action_triggered = False

    # --- MAIN LOGIC EXECUTION ---

    # 1. READ/GAME MODE
    if state.read_mode_active:
        pause_cursor = True

        # Only execute logic if NOT currently trying to exit via Spider-Man gesture
        if num_hands == 1 and hold_display_text == "":
            lms = hand_res.multi_hand_landmarks[0].landmark
            states, open_count = get_finger_states(lms)

            if open_count == 1 and states[4]:  # Pinky Only
                current_mode = "READ/GAME: NAV"
                state.last_pinky_nav_time = time.time()
                state.pinky_clicked = False
                state.cursor_x += (np.interp(lms[20].x, (0.2, 0.8), (0, screen_w)) - state.cursor_x) / SMOOTHING
                state.cursor_y += (np.interp(lms[20].y, (0.2, 0.8), (0, screen_h)) - state.cursor_y) / SMOOTHING
                pyautogui.moveTo(int(state.cursor_x), int(state.cursor_y))

            elif open_count == 0:  # Fist
                time_since_nav = time.time() - state.last_pinky_nav_time
                if time_since_nav < 0.8:
                    current_mode = "READ/GAME: CLICKING"
                    if not state.pinky_clicked:
                        pyautogui.click()
                        state.pinky_clicked = True
                else:
                    current_mode = "READ/GAME: SCROLL DOWN"
                    if time.time() - state.last_scroll_time > 0.1:
                        pyautogui.scroll(-READ_SCROLL_SPEED)
                        state.last_scroll_time = time.time()

            elif open_count >= 4:  # Open Hand
                current_mode = "READ/GAME: SCROLL UP"
                if time.time() - state.last_scroll_time > 0.1:
                    pyautogui.scroll(READ_SCROLL_SPEED)
                    state.last_scroll_time = time.time()

    # 2. GAME MODE
    elif state.game_mode_active:
        pause_cursor = True
        is_game_paused = False

        # Internal Emergency Exit Check (Index + Pinky)
        if num_hands == 1:
            lms = hand_res.multi_hand_landmarks[0].landmark
            st, oc = get_finger_states(lms)

            if st[1] and st[4] and not st[0] and not st[2] and not st[3]:
                is_game_paused = True
                current_mode = "GAME: PAUSED (HOLD TO EXIT)"
                if state.game_exit_start_time == 0.0: state.game_exit_start_time = time.time()
                hold_dur = time.time() - state.game_exit_start_time
                hold_display_text = f"EXITING GAME MODE: {hold_dur:.1f}s"

                if hold_dur >= 3.0:
                    state.game_mode_active = False
                    speak("GAME MODE DEACTIVATED BOSS")
                    state.game_exit_start_time = 0.0
            else:
                state.game_exit_start_time = 0.0
        else:
            state.game_exit_start_time = 0.0

        if not is_game_paused and state.game_mode_active and hold_display_text == "":

            # Dual Hand Controls
            if num_hands == 2:
                hand1 = hand_res.multi_hand_landmarks[0].landmark
                hand2 = hand_res.multi_hand_landmarks[1].landmark
                _, open_count1 = get_finger_states(hand1)
                _, open_count2 = get_finger_states(hand2)

                if open_count1 >= 4 and open_count2 >= 4:
                    current_mode = "GAME: UP ARROW"
                    if time.time() - state.last_action_time > 0.5:
                        pyautogui.press('up')
                        state.last_action_time = time.time()
                elif open_count1 == 0 and open_count2 == 0:
                    current_mode = "GAME: DOWN ARROW"
                    if time.time() - state.last_action_time > 0.5:
                        pyautogui.press('down')
                        state.last_action_time = time.time()

            # Single Hand Controls
            elif num_hands == 1:
                lms = hand_res.multi_hand_landmarks[0].landmark
                states, open_count = get_finger_states(lms)
                hand_cx = lms[9].x

                if open_count == 1 and states[4]:
                    current_mode = "GAME: PINKY NAV"
                    state.last_pinky_nav_time = time.time()
                    state.pinky_clicked = False
                    state.cursor_x += (np.interp(lms[20].x, (0.2, 0.8), (0, screen_w)) - state.cursor_x) / SMOOTHING
                    state.cursor_y += (np.interp(lms[20].y, (0.2, 0.8), (0, screen_h)) - state.cursor_y) / SMOOTHING
                    pyautogui.moveTo(int(state.cursor_x), int(state.cursor_y))

                elif open_count == 0 and time.time() - state.last_pinky_nav_time < 0.8:
                    current_mode = "GAME: CLICKING"
                    if not state.pinky_clicked:
                        pyautogui.click()
                        state.pinky_clicked = True

                elif open_count >= 2:
                    if hand_cx < 0.5:
                        current_mode = "GAME: LEFT ARROW (SECTOR 1)"
                        if time.time() - state.last_action_time > 0.5:
                            pyautogui.press('left')
                            state.last_action_time = time.time()
                    else:
                        current_mode = "GAME: RIGHT ARROW (SECTOR 2)"
                        if time.time() - state.last_action_time > 0.5:
                            pyautogui.press('right')
                            state.last_action_time = time.time()

    # 3. STANDARD CONTROLS
    else:
        drag_triggered = False

        if hand_res.multi_hand_landmarks and hold_display_text == "":
            for hand in hand_res.multi_hand_landmarks:
                lms = hand.landmark
                states, open_count = get_finger_states(lms)
                thumb, index, middle, ring, pinky = states
                hand_cx = lms[9].x

                if open_count == 5:
                    current_mode = "SYS: VOLUME CONTROL"
                    state.ui_meter_type = "VOLUME"
                    state.ui_meter_val = hand_cx

                    if hand_cx < 0.4 and time.time() - state.last_vol_time > 0.05:
                        pyautogui.press('volumedown')
                        state.last_vol_time = time.time()
                    elif hand_cx > 0.6 and time.time() - state.last_vol_time > 0.05:
                        pyautogui.press('volumeup')
                        state.last_vol_time = time.time()

                elif open_count == 4 and not thumb and SBC_AVAILABLE:
                    current_mode = "SYS: BRIGHTNESS CONTROL"
                    state.ui_meter_type = "BRIGHTNESS"
                    state.ui_meter_val = hand_cx

                    try:
                        curr_b = sbc.get_brightness()[0]
                        if hand_cx < 0.4 and time.time() - state.last_bright_time > 0.1:
                            sbc.set_brightness(max(0, curr_b - 5))
                            state.last_bright_time = time.time()
                        elif hand_cx > 0.6 and time.time() - state.last_bright_time > 0.1:
                            sbc.set_brightness(min(100, curr_b + 5))
                            state.last_bright_time = time.time()
                    except:
                        pass

                elif thumb and not index and not middle and not ring and not pinky:
                    current_mode = "SYS: DRAGGING"
                    pause_cursor = False
                    drag_triggered = True
                    if not state.is_dragging:
                        pyautogui.mouseDown()
                        state.is_dragging = True

                elif not thumb and not ring and not pinky:

                    if index and middle:
                        current_mode = "SYS: NAVIGATE"
                        pause_cursor = False
                        state.l_click_armed = True
                        state.r_click_armed = True

                    elif not index and middle:
                        current_mode = "SYS: LEFT CLICK"
                        pause_cursor = False
                        if state.l_click_armed:
                            pyautogui.click(button='left')
                            state.l_click_armed = False

                    elif index and not middle:
                        current_mode = "SYS: RIGHT CLICK"
                        pause_cursor = False
                        if state.r_click_armed:
                            pyautogui.click(button='right')
                            state.r_click_armed = False

        if state.is_dragging and not drag_triggered:
            pyautogui.mouseUp()
            state.is_dragging = False

    # FACE CURSOR FALLBACK
    if face_res.multi_face_landmarks and not pause_cursor:
        nose = face_res.multi_face_landmarks[0].landmark[1]
        state.cursor_x += (np.interp(nose.x, (0.35, 0.65), (0, screen_w)) - state.cursor_x) / SMOOTHING
        state.cursor_y += (np.interp(nose.y, (0.35, 0.65), (0, screen_h)) - state.cursor_y) / SMOOTHING
        pyautogui.moveTo(int(state.cursor_x), int(state.cursor_y))

    # Render Graphics
    frame = draw_cinematic_hud(frame, face_res, hand_res, current_mode, hold_display_text)

    cv2.imshow("AetherControl - Mark XXI (FRIDAY)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

tts_queue.put(None)
cap.release()
cv2.destroyAllWindows()
