document.addEventListener("DOMContentLoaded", function () {
  let storedFilename = null;
  resetForm();
  document.getElementById("romfile").value = "";

  function resetForm() {
    document.getElementById("error-message").classList.add("hidden");
    document.getElementById("detected-game").classList.add("hidden");
    document.getElementById("game-name").textContent = "";
    document.getElementById("box-art").classList.add("hidden");
    document.getElementById("box-art").src = "";
    document.getElementById("preset").innerHTML = "";
    document.getElementById("stored_filename").value = "";
  }

  // Compute SHA-256 checksum on the first `bytesToRead` bytes (default 1MB)
  async function computeChecksum(file, bytesToRead = 1048576) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = function (e) {
        const buffer = e.target.result;
        crypto.subtle
          .digest("SHA-256", buffer)
          .then((hashBuffer) => {
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            const hashHex = hashArray
              .map((b) => b.toString(16).padStart(2, "0"))
              .join("");
            resolve(hashHex);
          })
          .catch(reject);
      };
      reader.onerror = reject;
      // Read only the first bytesToRead bytes or the entire file if it's smaller
      const blob = file.slice(0, Math.min(bytesToRead, file.size));
      reader.readAsArrayBuffer(blob);
    });
  }

  function getFileExtension(filename) {
    const parts = filename.split(".");
    return parts[parts.length - 1].toLowerCase();
  }

  const allowedExtensions = ["gba", "gbc", "nds"];
  async function check_file(e)
  {
    resetForm();
    const file = e.target.files[0];
    if (!file) return;

    const filename = file.name.toLowerCase();
    const ext = getFileExtension(filename);

    // Check if the file extension is allowed.
    if (!allowedExtensions.includes(ext)) {
      const errorMessage = "Only GBA, GBC, and NDS files are supported.";
      document.getElementById("error-message").textContent = errorMessage;
      document.getElementById("error-message").classList.remove("hidden");
      // Clear the file input so the user must choose a valid file.
      romfileInput.value = "";
      return;
    }

    try {
      // Compute checksum from the first 1024 bytes
      const checksum = await computeChecksum(file);
      const ext = getFileExtension(filename);
      storedFilename = `${checksum}.${ext}`;

      // Check if the ROM is already on the server
      let response = await fetch("/check_rom", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checksum, ext }),
      });
      let data = await response.json();
      if (!data.exists) {
        // Upload the file since it doesn't exist yet
        const formData = new FormData();
        formData.append("checksum", checksum);
        formData.append("ext", ext);
        formData.append("romfile", file);
        response = await fetch("/upload_rom", {
          method: "POST",
          body: formData,
        });
        data = await response.json();
        if (!data.success) {
          throw new Error(data.error || "File upload failed.");
        }
        storedFilename = data.stored_filename;
      } else {
        storedFilename = data.stored_filename;
      }
      document.getElementById("stored_filename").value = storedFilename;

      // Get game identification and available presets
      response = await fetch("/get_presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stored_filename: storedFilename }),
      });
      data = await response.json();
      if (data.error) {
        throw new Error(data.error);
      }
      document.getElementById("game-name").textContent = data.game;
      document.getElementById("detected-game").classList.remove("hidden");

      const sanitizedGameName = data.game.toLowerCase().replace(/\s/g, "");
      document.getElementById(
        "box-art"
      ).src = `/static/boxart/${sanitizedGameName}.png`;
      document.getElementById("box-art").classList.remove("hidden");

      // Populate the preset dropdown
      const presetSelect = document.getElementById("preset");
      presetSelect.innerHTML = "";
      data.presets.forEach((preset) => {
        const option = document.createElement("option");
        option.value = preset;
        option.textContent = preset;
        presetSelect.appendChild(option);
      });
    } catch (err) {
      document.getElementById("error-message").textContent = err.message;
      document.getElementById("error-message").classList.remove("hidden");
      console.error(err);
      document.getElementById("romfile").value = "";
    }
  }
  const romfileInput = document.getElementById("romfile");
  romfileInput.addEventListener("change", check_file)
    const romfileSelectInput = document.getElementById("romfileselect");
  romfileSelectInput.addEventListener("change", check_file)

  const randomizerForm = document.getElementById("randomizer-form");
  randomizerForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!storedFilename) {
      alert("No ROM has been uploaded. Please select a file first.");
      return;
    }
    const formData = new FormData(randomizerForm);
    formData.set("stored_filename", storedFilename);
    try {
      document.getElementById("status-message").classList.remove("hidden");
      const response = await fetch("/randomize", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (data.error) {
        alert(data.error);
      } else if (data.success && data.download_url) {
        window.location.href = data.download_url;
      }
    } catch (err) {
      alert("Error processing request.");
      console.error(err);
    } finally {
      document.getElementById("status-message").classList.add("hidden");
      document.getElementById("romfile").value = "";
      resetForm();
    }
  });
});
