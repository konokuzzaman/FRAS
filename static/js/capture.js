const captureVideo = document.getElementById('capture-video');
const captureBtn = document.getElementById('capture-btn');
const captureStatus = document.getElementById('capture-status');

if (captureVideo && captureBtn) {
  navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
      captureVideo.srcObject = stream;
    })
    .catch(err => {
      console.error('Webcam error:', err);
      if (captureStatus) {
        captureStatus.textContent = 'Cannot access webcam. Please allow camera permissions.';
      }
    });

  captureBtn.addEventListener('click', () => {
    const canvas = document.createElement('canvas');
    canvas.width = captureVideo.videoWidth;
    canvas.height = captureVideo.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(captureVideo, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(blob => {
      const formData = new FormData();
      formData.append('file', blob, 'capture.jpg');

      fetch(window.location.href, { method: 'POST', body: formData })
        .then(res => {
          if (captureStatus) {
            captureStatus.textContent = res.ok ? 'Face captured successfully!' : 'Capture failed.';
          }
          if (res.ok) {
            setTimeout(() => window.location.href = '/students', 1200);
          }
        })
        .catch(err => {
          console.error(err);
          if (captureStatus) {
            captureStatus.textContent = 'Capture failed.';
          }
        });
    }, 'image/jpeg', 0.92);
  });
}
