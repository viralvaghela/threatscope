// chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
//     if (message.action === 'analyzePage') {
//       const analysis = {
//         url: window.location.href,
//         urlSecure: window.location.protocol === 'https:',
//         forms: [],
//         scriptInsights: [],
//         notes: []
//       };
  
//       // Group inputs by form
//       const forms = document.querySelectorAll('form');
//       forms.forEach(form => {
//         const fields = form.querySelectorAll('input, textarea, select');
//         const formFields = [];
  
//         fields.forEach(el => {
//           formFields.push({
//             tag: el.tagName.toLowerCase(),
//             name: el.name || '',
//             id: el.id || '',
//             type: el.type || '',
//             placeholder: el.placeholder || ''
//           });
//         });
  
//         analysis.forms.push({
//           formAction: form.action || '',
//           method: form.method || 'GET',
//           inputs: formFields
//         });
  
//         if (form.action.startsWith('http://')) {
//           analysis.notes.push(`⚠️ Form action points to insecure HTTP: ${form.action}`);
//         }
//       });
  
//       // URL Security check
//       if (!analysis.urlSecure) {
//         analysis.notes.push(`⚠️ Page is served over insecure HTTP: ${analysis.url}`);
//       }
  
//       // Look for XHR/fetch/axios
//       const scripts = document.querySelectorAll('script');
//       scripts.forEach(script => {
//         const code = script.textContent || '';
//         if (/fetch\s*\(|XMLHttpRequest|axios/i.test(code)) {
//           analysis.scriptInsights.push(code.slice(0, 300)); // trim long scripts
//           analysis.notes.push("ℹ️ JS sending data detected via fetch/XHR.");
//         }
//       });
  
//       sendResponse(analysis);
//     }
//   });
  


chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'analyzePage') {
    const analysis = {
      url: window.location.href,
      urlSecure: window.location.protocol === 'https:',
      forms: [],
      scriptInsights: [],
      notes: []
    };

    // Group inputs by form
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
      const fields = form.querySelectorAll('input, textarea, select');
      const formFields = [];

      fields.forEach(el => {
        formFields.push({
          tag: el.tagName.toLowerCase(),
          name: el.name || '',
          id: el.id || '',
          type: el.type || '',
          placeholder: el.placeholder || ''
        });
      });

      analysis.forms.push({
        formAction: form.action || '',
        method: form.method || 'GET',
        inputs: formFields
      });

      if (form.action.startsWith('http://')) {
        analysis.notes.push(`⚠️ Form action points to insecure HTTP: ${form.action}`);
      }
    });

    // URL Security check
    if (!analysis.urlSecure) {
      analysis.notes.push(`⚠️ Page is served over insecure HTTP: ${analysis.url}`);
    }

    // Look for XHR/fetch/axios
    const scripts = document.querySelectorAll('script');
    scripts.forEach(script => {
      const code = script.textContent || '';
      if (/fetch\s*\(|XMLHttpRequest|axios/i.test(code)) {
        analysis.scriptInsights.push(code.slice(0, 300)); // trim long scripts
        analysis.notes.push("ℹ️ JS sending data detected via fetch/XHR.");
      }
    });

    sendResponse(analysis);
  }
});
