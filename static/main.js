function validateUrl(url) {
  // Simple URL validation
  const pattern = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([\/\w .-]*)*\/?$/;
  return pattern.test(url);
}

document.getElementById('urlForm').onsubmit = function(event) {
  const urlInput = document.getElementById('url');
  if (!validateUrl(urlInput.value)) {
    event.preventDefault(); // Stop form submission
    $('#urlValidationModal').modal('show'); // Show the modal
  }
};

document.getElementById('confirmUrl').onclick = function() {
  // Add a hidden input to indicate the user has confirmed the URL
  const confirmInput = document.createElement('input');
  confirmInput.type = 'hidden';
  confirmInput.name = 'confirmUrl';
  confirmInput.value = 'true';
  document.getElementById('urlForm').appendChild(confirmInput);
  document.getElementById('urlForm').submit(); // Submit the form
};