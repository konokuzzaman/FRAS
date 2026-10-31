const liveVideo = document.getElementById('live-video');
const overlayCanvas = document.getElementById('video-overlay');
const startBtn = document.getElementById('start-session');
const stopBtn = document.getElementById('stop-session');
const liveStatus = document.getElementById('live-status');
const sectionSelect = document.getElementById('section-select');
const manualSection = document.getElementById('manual-section');
const manualStudent = document.getElementById('manual-student');
const manualSessionInput = document.getElementById('manual-session-id');

let recognitionInterval = null;
let sessionId = null;

const overlayCtx = overlayCanvas ? overlayCanvas.getContext('2d') : null;

async function initCamera() {
  if (!liveVideo) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    liveVideo.srcObject = stream;
  } catch (err) {
    console.error('Webcam error:', err);
    if (liveStatus) {
      liveStatus.textContent = 'Cannot access webcam. Please enable camera permissions.';
    }
  }
}

function drawFaces(payload) {
  if (!overlayCanvas || !overlayCtx || !payload) return;
  overlayCanvas.width = liveVideo.clientWidth || liveVideo.videoWidth;
  overlayCanvas.height = liveVideo.clientHeight || liveVideo.videoHeight;
  overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  if (!payload.faces || !payload.frame) return;
  const scaleX = overlayCanvas.width / payload.frame.width;
  const scaleY = overlayCanvas.height / payload.frame.height;
  overlayCtx.font = '14px Space Grotesk';
  overlayCtx.lineWidth = 2;
  payload.faces.forEach(face => {
    const x = face.box.left * scaleX;
    const y = face.box.top * scaleY;
    const w = face.box.width * scaleX;
    const h = face.box.height * scaleY;
    overlayCtx.strokeStyle = face.type === 'recognized' ? '#3dd598' : '#ff5c5c';
    overlayCtx.strokeRect(x, y, w, h);
    const label = face.name || 'Unknown';
    const labelWidth = overlayCtx.measureText(label).width + 16;
    overlayCtx.fillStyle = 'rgba(7,8,18,0.75)';
    overlayCtx.fillRect(x, Math.max(y - 26, 0), labelWidth, 22);
    overlayCtx.fillStyle = '#fff';
    overlayCtx.fillText(label, x + 8, Math.max(y - 10, 14));
  });
}

async function sendFrame() {
  if (!liveVideo || !sectionSelect || !sectionSelect.value || !sessionId || liveVideo.readyState < 2) return;
  const canvas = document.createElement('canvas');
  canvas.width = liveVideo.videoWidth;
  canvas.height = liveVideo.videoHeight;
  canvas.getContext('2d').drawImage(liveVideo, 0, 0);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));
  const formData = new FormData();
  formData.append('frame', blob, 'frame.jpg');
  formData.append('section_id', sectionSelect.value);
  formData.append('session_id', sessionId);
  try {
    const res = await fetch('/recognize_frame', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.status === 'processed') {
      drawFaces(data);
      if (liveStatus) {
        liveStatus.textContent = `Smart attendance · Recognized ${data.recognized} · Unknown ${data.unknown}`;
      }
    } else if (data.status === 'no_face' && liveStatus) {
      liveStatus.textContent = 'Camera ready · No face detected';
      overlayCtx && overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    }
  } catch (err) {
    console.error(err);
    if (liveStatus) {
      liveStatus.textContent = 'Recognition error. Check connection.';
    }
  }
}

async function startSession() {
  if (!sectionSelect.value) {
    liveStatus && (liveStatus.textContent = 'Select a section to begin.');
    return;
  }
  try {
    const res = await fetch('/api/attendance_sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        section_id: Number(sectionSelect.value),
        mode: 'smart',
        device_name: navigator.userAgent
      })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || 'Unable to start session.');
    }
    sessionId = data.session_id;
    if (manualSessionInput) manualSessionInput.value = sessionId || '';
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;
    if (liveStatus) liveStatus.textContent = 'Session started · scanning faces...';
    recognitionInterval = setInterval(sendFrame, 1800);
  } catch (err) {
    console.error(err);
    liveStatus && (liveStatus.textContent = 'Unable to start session.');
  }
}

async function stopSession() {
  if (!sessionId) return;
  clearInterval(recognitionInterval);
  recognitionInterval = null;
  try {
    await fetch(`/api/attendance_sessions/${sessionId}/close`, { method: 'POST' });
  } catch (err) {
    console.error(err);
  }
  sessionId = null;
  if (manualSessionInput) manualSessionInput.value = '';
  if (liveStatus) liveStatus.textContent = 'Session closed.';
  overlayCtx && overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  if (startBtn) startBtn.disabled = false;
  if (stopBtn) stopBtn.disabled = true;
}

async function loadStudents(sectionId) {
  if (!sectionId || !manualStudent) return;
  manualStudent.innerHTML = '<option value="">Loading...</option>';
  const res = await fetch(`/api/sections/${sectionId}/students`);
  if (!res.ok || res.redirected) return;
  const students = await res.json();
  manualStudent.innerHTML = '<option value="">Select student</option>';
  students.forEach(stu => {
    const option = document.createElement('option');
    option.value = stu.student_id;
    option.textContent = `${stu.roll} · ${stu.name}`;
    manualStudent.appendChild(option);
  });
}

if (liveVideo) {
  initCamera();
}

if (startBtn) {
  startBtn.addEventListener('click', startSession);
}

if (stopBtn) {
  stopBtn.addEventListener('click', stopSession);
}

if (manualSection) {
  manualSection.addEventListener('change', e => loadStudents(e.target.value));
  if (manualSection.value) {
    loadStudents(manualSection.value);
  }
}

if (sectionSelect && manualSection) {
  sectionSelect.addEventListener('change', e => {
    manualSection.value = e.target.value;
    manualSection.dispatchEvent(new Event('change'));
  });
}
