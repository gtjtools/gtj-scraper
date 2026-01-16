let allData = [];
let currentData = [];

// DOM elements - Part 135
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const clearBtn = document.getElementById('clearBtn');
const totalRecords = document.getElementById('totalRecords');
const loading = document.getElementById('loading');
const errorDiv = document.getElementById('error');
const tableHead = document.getElementById('tableHead');
const tableBody = document.getElementById('tableBody');

// DOM elements - Charter
const charterSearchInput = document.getElementById('charterSearchInput');
const charterLoading = document.getElementById('charterLoading');
const charterError = document.getElementById('charterError');
const charterResults = document.getElementById('charterResults');
const charterList = document.getElementById('charterList');
const charterStats = document.getElementById('charterStats');

// Charter companies data
let charterCompanies = [];
let filteredCharterCompanies = [];

// DOM elements - Modal
const modal = document.getElementById('detailsModal');
const modalBody = document.getElementById('modalBody');
const closeModal = document.getElementsByClassName('close')[0];

// DOM elements - Tail Search
const tailSearchInput = document.getElementById('tailSearchInput');
const tailSearchBtn = document.getElementById('tailSearchBtn');
const tailClearBtn = document.getElementById('tailClearBtn');
const tailLoading = document.getElementById('tailLoading');
const tailError = document.getElementById('tailError');
const tailResults = document.getElementById('tailResults');

// Mode tabs
const modeTabs = document.querySelectorAll('.mode-tab');
const sections = {
  part135: document.getElementById('part135Section'),
  charter: document.getElementById('charterSection'),
  tail: document.getElementById('tailSection'),
};

// Load data on page load
async function loadData() {
  try {
    loading.style.display = 'block';
    errorDiv.style.display = 'none';

    const response = await fetch('/api/operators');
    if (!response.ok) {
      throw new Error('Failed to load data');
    }

    const result = await response.json();
    allData = result.data;
    currentData = allData;

    displayData(currentData);
    updateStats();

    loading.style.display = 'none';
  } catch (error) {
    console.error('Error loading data:', error);
    loading.style.display = 'none';
    errorDiv.textContent = 'Error loading data: ' + error.message;
    errorDiv.style.display = 'block';
  }
}

// Group data by certificate holder and district
function groupData(data) {
  const grouped = {};

  data.forEach((record) => {
    const holderName = record['Part 135 Certificate Holder Name'] || 'Unknown';
    const district =
      record['FAA Certificate Holding District Office'] || 'Unknown';

    if (!grouped[holderName]) {
      grouped[holderName] = {
        name: holderName,
        certificateDesignator: record['Certificate Designator'],
        districts: {},
      };
    }

    if (!grouped[holderName].districts[district]) {
      grouped[holderName].districts[district] = [];
    }

    grouped[holderName].districts[district].push(record);
  });

  return grouped;
}

// Display data in grouped table
function displayData(data) {
  if (data.length === 0) {
    tableHead.innerHTML = '';
    tableBody.innerHTML =
      '<tr><td colspan="100" style="text-align: center; padding: 40px;">No data found</td></tr>';
    return;
  }

  // Group the data
  const grouped = groupData(data);
  const holderNames = Object.keys(grouped).sort();

  // Create table headers
  tableHead.innerHTML = `
        <tr>
            <th>Certificate Holder</th>
            <th>Certificate Designator</th>
            <th>Aircraft Count</th>
            <th>Actions</th>
        </tr>
    `;

  // Create table rows for each holder
  tableBody.innerHTML = holderNames
    .map((holderName) => {
      const holder = grouped[holderName];
      const totalAircraft = Object.values(holder.districts).reduce(
        (sum, aircraft) => sum + aircraft.length,
        0
      );
      const districts = Object.keys(holder.districts);
      const holderId = holderName.replace(/[^a-zA-Z0-9]/g, '_');

      return `
            <tr class="holder-row" onclick="toggleHolder('${holderId}')">
                <td>
                    <span class="expand-icon" id="icon-${holderId}">▶</span>
                    <strong>${escapeHtml(holderName)}</strong>
                </td>
                <td>${escapeHtml(holder.certificateDesignator || 'N/A')}</td>
                <td>${totalAircraft} aircraft</td>
                <td>
                    <button class="view-details-btn" onclick="event.stopPropagation(); viewDetails(0, '${escapeHtml(
                      holderName.replace(/'/g, "\\'")
                    )}')">
                        View Details
                    </button>
                </td>
            </tr>
            <tr class="nested-container" id="nested-${holderId}" style="display: none;">
                <td colspan="4">
                    <div class="nested-content">
                        ${districts
                          .map((district) => {
                            const aircraft = holder.districts[district];
                            return `
                                <div class="district-section">
                                    <h4 class="district-title">${escapeHtml(
                                      district
                                    )} (${aircraft.length} aircraft)</h4>
                                    <table class="aircraft-table">
                                        <thead>
                                            <tr>
                                                <th>Registration Number</th>
                                                <th>Aircraft Make/Model/Series</th>
                                                <th>Serial Number</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${aircraft
                                              .map(
                                                (a) => `
                                                <tr>
                                                    <td>${escapeHtml(
                                                      a[
                                                        'Registration Number'
                                                      ] || 'N/A'
                                                    )}</td>
                                                    <td>${escapeHtml(
                                                      a[
                                                        'Aircraft Make/Model/Series'
                                                      ] || 'N/A'
                                                    )}</td>
                                                    <td>${escapeHtml(
                                                      String(
                                                        a['Serial Number'] ||
                                                          'N/A'
                                                      )
                                                    )}</td>
                                                </tr>
                                            `
                                              )
                                              .join('')}
                                        </tbody>
                                    </table>
                                </div>
                            `;
                          })
                          .join('')}
                    </div>
                </td>
            </tr>
        `;
    })
    .join('');
}

// Toggle holder expansion
function toggleHolder(holderId) {
  const nested = document.getElementById(`nested-${holderId}`);
  const icon = document.getElementById(`icon-${holderId}`);

  if (nested.style.display === 'none') {
    nested.style.display = 'table-row';
    icon.textContent = '▼';
  } else {
    nested.style.display = 'none';
    icon.textContent = '▶';
  }
}

// Extract operator name from record
function getOperatorName(record) {
  // Try common field names
  const possibleFields = [
    'Legal Name',
    'Operator Name',
    'Name',
    'Company Name',
    'Company',
  ];

  for (const field of possibleFields) {
    if (record[field]) {
      return String(record[field]).replace(/'/g, "\\'");
    }
  }

  // Fallback to first non-empty value
  const values = Object.values(record);
  for (const val of values) {
    if (val && String(val).trim()) {
      return String(val).replace(/'/g, "\\'");
    }
  }

  return 'Unknown';
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Update statistics
function updateStats() {
  const grouped = groupData(currentData);
  const holderCount = Object.keys(grouped).length;
  const totalGrouped = groupData(allData);
  const totalHolders = Object.keys(totalGrouped).length;

  totalRecords.textContent = `Showing ${holderCount} certificate holders (${currentData.length} aircraft) of ${totalHolders} total holders (${allData.length} aircraft)`;
}

// Search functionality
async function performSearch() {
  const query = searchInput.value.trim();

  if (!query) {
    currentData = allData;
    displayData(currentData);
    updateStats();
    return;
  }

  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
    if (!response.ok) {
      throw new Error('Search failed');
    }

    const result = await response.json();
    currentData = result.data;
    displayData(currentData);
    updateStats();
  } catch (error) {
    console.error('Search error:', error);
    errorDiv.textContent = 'Search error: ' + error.message;
    errorDiv.style.display = 'block';
  }
}

// Clear search
function clearSearch() {
  searchInput.value = '';
  currentData = allData;
  displayData(currentData);
  updateStats();
}

// View operator details with enriched data
async function viewDetails(index, operatorName) {
  const record = currentData[index];

  // Show modal with loading state
  modal.style.display = 'block';
  modalBody.innerHTML =
    '<div class="loading-modal">Loading operator details...</div>';

  try {
    // Fetch enriched data from Business Air News
    const response = await fetch(
      `/api/enrich/${encodeURIComponent(operatorName)}`
    );
    const enrichResult = await response.json();

    // Build modal content
    let content = `
            <div class="detail-section">
                <h2>${escapeHtml(operatorName)}</h2>
                ${
                  enrichResult.found
                    ? '<span class="enrichment-badge">Enhanced Data Available</span>'
                    : ''
                }
            </div>

            <div class="detail-section">
                <h3>FAA Data</h3>
                <div class="detail-grid">
                    ${Object.entries(record)
                      .map(
                        ([key, value]) => `
                        <div class="detail-item">
                            <label>${escapeHtml(key)}:</label>
                            <div>${escapeHtml(value ?? 'N/A')}</div>
                        </div>
                    `
                      )
                      .join('')}
                </div>
            </div>
        `;

    if (enrichResult.found && enrichResult.data) {
      const data = enrichResult.data;

      // Certifications
      content += `
                <div class="detail-section">
                    <h2>Certifications</h2>
                    <div class="detail-grid">
                        <div class="detail-item">
                            <label>AOC/Part 135:</label>
                            <div>${escapeHtml(
                              data.certifications.aoc_part135 || 'N/A'
                            )}</div>
                        </div>
                        <div class="detail-item">
                            <label>Wyvern Certified:</label>
                            <div>${escapeHtml(
                              data.certifications.wyvern_certified || 'N/A'
                            )}</div>
                        </div>
                        <div class="detail-item">
                            <label>ARGUS Rating:</label>
                            <div>${escapeHtml(
                              data.certifications.argus_rating || 'N/A'
                            )}</div>
                        </div>
                        <div class="detail-item">
                            <label>IS-BAO:</label>
                            <div>${escapeHtml(
                              data.certifications.is_bao || 'N/A'
                            )}</div>
                        </div>
                        <div class="detail-item">
                            <label>ACSF IAS:</label>
                            <div>${escapeHtml(
                              data.certifications.acsf_ias || 'N/A'
                            )}</div>
                        </div>
                    </div>
                </div>
            `;

      // Contact Information
      content += `
                <div class="detail-section">
                    <h2>Contact Information</h2>
                    <div class="detail-grid">
                        <div class="detail-item">
                            <label>Telephone:</label>
                            <div>${escapeHtml(
                              data.contact.telephone || 'N/A'
                            )}</div>
                        </div>
                        <div class="detail-item">
                            <label>Email:</label>
                            <div>${
                              data.contact.email
                                ? `<a href="mailto:${escapeHtml(
                                    data.contact.email
                                  )}">${escapeHtml(data.contact.email)}</a>`
                                : 'N/A'
                            }</div>
                        </div>
                        <div class="detail-item">
                            <label>Website:</label>
                            <div>${
                              data.contact.website
                                ? `<a href="${escapeHtml(
                                    data.contact.website
                                  )}" target="_blank">${escapeHtml(
                                    data.contact.website
                                  )}</a>`
                                : 'N/A'
                            }</div>
                        </div>
                    </div>
                </div>
            `;

      // Charter Bases and Aircraft
      if (data.bases && data.bases.length > 0) {
        content += `
                    <div class="detail-section">
                        <h2>Charter Bases and Aircraft</h2>
                        ${data.bases
                          .map(
                            (base) => `
                            <div class="base-item">
                                <strong>${escapeHtml(
                                  base.location
                                )}</strong><br>
                                ${escapeHtml(base.aircraft)}
                                ${
                                  base.type
                                    ? `<br><em>${escapeHtml(base.type)}</em>`
                                    : ''
                                }
                            </div>
                        `
                          )
                          .join('')}
                    </div>
                `;
      }

      // Source link
      if (data.url) {
        content += `
                    <div class="detail-section">
                        <p><a href="${escapeHtml(
                          data.url
                        )}" target="_blank">View on Business Air News →</a></p>
                    </div>
                `;
      }
    } else if (enrichResult.found === false) {
      content += `
                <div class="detail-section">
                    <p style="color: #e74c3c;">No additional information found on Business Air News.</p>
                </div>
            `;
    }

    modalBody.innerHTML = content;
  } catch (error) {
    console.error('Error loading details:', error);
    modalBody.innerHTML = `
            <div class="detail-section">
                <h2>${escapeHtml(operatorName)}</h2>
            </div>
            <div style="color: #e74c3c; text-align: center; padding: 20px;">
                Error loading enriched data. Showing FAA data only.
            </div>
            <div class="detail-section">
                <h3>FAA Data</h3>
                <div class="detail-grid">
                    ${Object.entries(record)
                      .map(
                        ([key, value]) => `
                        <div class="detail-item">
                            <label>${escapeHtml(key)}:</label>
                            <div>${escapeHtml(value ?? 'N/A')}</div>
                        </div>
                    `
                      )
                      .join('')}
                </div>
            </div>
        `;
  }
}

// Modal close handlers
closeModal.onclick = function () {
  modal.style.display = 'none';
};

window.onclick = function (event) {
  if (event.target == modal) {
    modal.style.display = 'none';
  }
};

// Mode switching
modeTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    const mode = tab.dataset.mode;

    // Update active tab
    modeTabs.forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');

    // Update active section
    Object.keys(sections).forEach((key) => {
      sections[key].classList.remove('active');
    });
    sections[mode].classList.add('active');
  });
});

// Load charter companies (enriched with scores)
async function loadCharterCompanies() {
  try {
    charterLoading.style.display = 'block';
    charterError.style.display = 'none';

    const response = await fetch('/api/charter/operators');
    if (!response.ok) {
      throw new Error('Failed to load charter operators');
    }

    const result = await response.json();
    charterCompanies = result.data;
    filteredCharterCompanies = charterCompanies;

    displayCharterList(filteredCharterCompanies);
    updateCharterStats();

    charterLoading.style.display = 'none';
  } catch (error) {
    console.error('Error loading charter operators:', error);
    charterLoading.style.display = 'none';
    charterError.textContent = 'Error loading charter operators';
    charterError.style.display = 'block';
  }
}

// Display charter companies list with scores
function displayCharterList(companies) {
  charterList.innerHTML = companies
    .map((company, index) => {
      const score = company.score || 0;
      const scoreClass =
        score >= 150
          ? 'score-high'
          : score >= 100
          ? 'score-medium'
          : 'score-low';
      const part135 = company.part135_cert || 'N/A';
      const faaLinked = company.faa_data ? '✓ FAA Linked' : '';

      // Get certification badges
      const certs = company.data?.certifications || {};
      const certBadges = [];
      if (
        certs.argus_rating &&
        certs.argus_rating.toLowerCase().includes('platinum')
      )
        certBadges.push('ARGUS Platinum');
      if (
        certs.argus_rating &&
        certs.argus_rating.toLowerCase().includes('gold')
      )
        certBadges.push('ARGUS Gold');
      if (
        certs.wyvern_certified &&
        certs.wyvern_certified !== 'No' &&
        certs.wyvern_certified !== 'N/A'
      )
        certBadges.push('Wyvern');
      if (certs.is_bao && certs.is_bao !== 'No' && certs.is_bao !== 'N/A')
        certBadges.push('IS-BAO');

      return `
            <div class="charter-company-card">
                <div class="company-header" onclick="loadCharterDetails(${index})">
                    <div>
                        <h3>${escapeHtml(
                          company.company
                        )} <span class="score-badge ${scoreClass}">Score: ${score}</span></h3>
                        <div class="company-meta">
                            <span class="part135-badge">Part 135: ${escapeHtml(
                              part135
                            )}</span>
                            ${
                              faaLinked
                                ? '<span class="faa-linked-badge">' +
                                  faaLinked +
                                  '</span>'
                                : ''
                            }
                        </div>
                    </div>
                </div>
                <div class="company-locations">
                    ${company.locations
                      .map(
                        (loc) =>
                          `<span class="location-badge">${escapeHtml(
                            loc
                          )}</span>`
                      )
                      .join('')}
                </div>
                ${
                  certBadges.length > 0
                    ? `
                    <div class="cert-badges">
                        ${certBadges
                          .map(
                            (cert) => `<span class="cert-badge">${cert}</span>`
                          )
                          .join('')}
                    </div>
                `
                    : ''
                }
                <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb;">
                    <button class="view-details-btn" onclick="event.stopPropagation(); runCharterScore('${escapeHtml(
                      company.company.replace(/'/g, "\\'")
                    )}', '${escapeHtml(
        (part135 || '').replace(/'/g, "\\'")
      )}', '${escapeHtml(
        (company.faa_state || '').replace(/'/g, "\\'")
      )}')" style="width: 100%;">
                        🚀 Run Full Verification (NTSB + UCC)
                    </button>
                </div>
            </div>
        `;
    })
    .join('');
}

// Update charter stats
function updateCharterStats() {
  charterStats.textContent = `Showing ${filteredCharterCompanies.length} of ${charterCompanies.length} charter operators`;
}

// Filter charter companies
function filterCharterCompanies() {
  const query = charterSearchInput.value.trim().toLowerCase();

  if (!query) {
    filteredCharterCompanies = charterCompanies;
  } else {
    filteredCharterCompanies = charterCompanies.filter(
      (company) =>
        company.company.toLowerCase().includes(query) ||
        company.locations.some((loc) => loc.toLowerCase().includes(query))
    );
  }

  displayCharterList(filteredCharterCompanies);
  updateCharterStats();
}

// Load charter details by index
async function loadCharterDetails(index) {
  const company = filteredCharterCompanies[index];

  if (!company.url) {
    charterError.textContent =
      'No Business Air News link available for this company';
    charterError.style.display = 'block';
    return;
  }

  try {
    charterLoading.style.display = 'block';
    charterError.style.display = 'none';
    charterResults.innerHTML = '';
    charterList.style.display = 'none';

    // Extract record number from URL
    const match = company.url.match(/recnum=(\d+)/);
    if (!match) {
      throw new Error('Invalid URL format');
    }

    const response = await fetch(`/api/charter/search/${match[1]}`);
    const result = await response.json();

    charterLoading.style.display = 'none';

    if (result.found && result.data) {
      displayCharterResult(result.data, result.cached, company.company);
    } else {
      charterError.textContent = result.message || 'No charter operator found';
      charterError.style.display = 'block';
      charterList.style.display = 'block';
    }
  } catch (error) {
    console.error('Charter details error:', error);
    charterLoading.style.display = 'none';
    charterError.textContent = 'Error loading charter operator details';
    charterError.style.display = 'block';
    charterList.style.display = 'block';
  }
}

function generateCharterResultHTML(data, isCached = false, companyName = null) {
  const displayName = companyName || data.name || 'Unknown Operator';
  return `
        <div class="charter-result-card">
            <h3>${escapeHtml(displayName)} ${
    data.country
      ? `<span class="country">(${escapeHtml(data.country)})</span>`
      : ''
  }${isCached ? '<span class="enrichment-badge">Pre-Scraped</span>' : ''}</h3>

            ${
              data.certifications
                ? `
                <div class="result-section">
                    <h4>Certifications</h4>
                    <div class="cert-grid">
                        ${
                          data.certifications.aoc_part135
                            ? `<div class="cert-item"><strong>AOC/Part 135:</strong> ${escapeHtml(
                                data.certifications.aoc_part135
                              )}</div>`
                            : ''
                        }
                        ${
                          data.certifications.wyvern_certified
                            ? `<div class="cert-item"><strong>Wyvern:</strong> ${escapeHtml(
                                data.certifications.wyvern_certified
                              )}</div>`
                            : ''
                        }
                        ${
                          data.certifications.argus_rating
                            ? `<div class="cert-item"><strong>ARGUS:</strong> ${escapeHtml(
                                data.certifications.argus_rating
                              )}</div>`
                            : ''
                        }
                        ${
                          data.certifications.is_bao
                            ? `<div class="cert-item"><strong>IS-BAO:</strong> ${escapeHtml(
                                data.certifications.is_bao
                              )}</div>`
                            : ''
                        }
                        ${
                          data.certifications.acsf_ias
                            ? `<div class="cert-item"><strong>ACSF IAS:</strong> ${escapeHtml(
                                data.certifications.acsf_ias
                              )}</div>`
                            : ''
                        }
                    </div>
                </div>
            `
                : ''
            }

            ${
              data.contact
                ? `
                <div class="result-section">
                    <h4>Contact Information</h4>
                    <div class="contact-grid">
                        ${
                          data.contact.telephone
                            ? `<div><strong>Phone:</strong> ${escapeHtml(
                                data.contact.telephone
                              )}</div>`
                            : ''
                        }
                        ${
                          data.contact.email
                            ? `<div><strong>Email:</strong> <a href="mailto:${escapeHtml(
                                data.contact.email
                              )}">${escapeHtml(data.contact.email)}</a></div>`
                            : ''
                        }
                        ${
                          data.contact.website
                            ? `<div><strong>Website:</strong> <a href="${escapeHtml(
                                data.contact.website
                              )}" target="_blank">${escapeHtml(
                                data.contact.website
                              )}</a></div>`
                            : ''
                        }
                    </div>
                </div>
            `
                : ''
            }

            ${
              data.bases && data.bases.length > 0
                ? `
                <div class="result-section">
                    <h4>Charter Bases & Aircraft</h4>
                    ${data.bases
                      .map(
                        (base) => `
                        <div class="base-card">
                            <strong>${escapeHtml(base.location)}</strong><br>
                            ${escapeHtml(base.aircraft)}
                            ${
                              base.type
                                ? `<br><em>${escapeHtml(base.type)}</em>`
                                : ''
                            }
                        </div>
                    `
                      )
                      .join('')}
                </div>
            `
                : ''
            }

            ${
              data.url
                ? `
                <div class="result-section">
                    <a href="${escapeHtml(
                      data.url
                    )}" target="_blank" class="view-source-btn">View on Business Air News →</a>
                </div>
            `
                : ''
            }
        </div>
    `;
}

// Event listeners - Part 135
searchBtn.addEventListener('click', performSearch);
clearBtn.addEventListener('click', clearSearch);
searchInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    performSearch();
  }
});

// Event listeners - Charter
charterSearchInput.addEventListener('input', filterCharterCompanies);

// Mode switching - load charter companies when switching to charter tab
modeTabs.forEach((tab) => {
  const originalListener = tab.onclick;
  tab.addEventListener('click', () => {
    const mode = tab.dataset.mode;
    if (mode === 'charter' && charterCompanies.length === 0) {
      loadCharterCompanies();
    }
  });
});

// Add back button to charter results
function displayCharterResult(data, isCached = false, companyName = null) {
  const html = `
        <div style="margin-bottom: 20px;">
            <button class="view-details-btn" onclick="backToCharterList()">← Back to List</button>
        </div>
        ${generateCharterResultHTML(data, isCached, companyName)}
    `;
  charterResults.innerHTML = html;
}

// Back to charter list
function backToCharterList() {
  charterResults.innerHTML = '';
  charterList.style.display = 'block';
}

// Load data on page load
loadData();

// Apply charter filters
async function applyCharterFilters() {
  try {
    const certFilter = document.getElementById('certFilter').value;
    const minScore = document.getElementById('minScoreFilter').value;

    charterLoading.style.display = 'block';
    charterError.style.display = 'none';

    const params = new URLSearchParams();
    if (certFilter) params.append('cert', certFilter);
    if (minScore) params.append('minScore', minScore);

    const response = await fetch(`/api/charter/filter?${params.toString()}`);
    if (!response.ok) {
      throw new Error('Failed to filter charter operators');
    }

    const result = await response.json();
    filteredCharterCompanies = result.data;

    displayCharterList(filteredCharterCompanies);
    updateCharterStats();

    charterLoading.style.display = 'none';
  } catch (error) {
    console.error('Error filtering charter operators:', error);
    charterLoading.style.display = 'none';
    charterError.textContent = 'Error applying filters';
    charterError.style.display = 'block';
  }
}

// Clear charter filters
function clearCharterFilters() {
  document.getElementById('certFilter').value = '';
  document.getElementById('minScoreFilter').value = '';
  filteredCharterCompanies = charterCompanies;
  displayCharterList(filteredCharterCompanies);
  updateCharterStats();
}

// Filter button event listeners
document
  .getElementById('applyFiltersBtn')
  ?.addEventListener('click', applyCharterFilters);
document
  .getElementById('clearFiltersBtn')
  ?.addEventListener('click', clearCharterFilters);

// Tail number search functionality
async function searchTailNumber() {
  const tailNumber = tailSearchInput.value.trim().toUpperCase();

  if (!tailNumber) {
    tailError.textContent = 'Please enter a tail number';
    tailError.style.display = 'block';
    return;
  }

  try {
    tailLoading.style.display = 'block';
    tailError.style.display = 'none';
    tailResults.innerHTML = '';

    const response = await fetch(
      `/api/search/tail/${encodeURIComponent(tailNumber)}`
    );
    const result = await response.json();

    tailLoading.style.display = 'none';

    if (result.found) {
      displayTailSearchResult(result);
    } else {
      tailError.textContent =
        result.message || 'No aircraft found with this tail number';
      tailError.style.display = 'block';
    }
  } catch (error) {
    console.error('Tail search error:', error);
    tailLoading.style.display = 'none';
    tailError.textContent = 'Error searching for tail number';
    tailError.style.display = 'block';
  }
}

// Display tail search results
function displayTailSearchResult(result) {
  const html = `
        <div class="charter-result-card">
            <h3>Tail Number: ${escapeHtml(result.tail_number)}</h3>

            ${
              result.aircraft && result.aircraft.length > 0
                ? `
                <div class="result-section">
                    <h4>Aircraft Details</h4>
                    ${result.aircraft
                      .map(
                        (aircraft) => `
                        <div class="base-card">
                            <strong>Make/Model:</strong> ${escapeHtml(
                              aircraft.make_model
                            )}<br>
                            <strong>Serial Number:</strong> ${escapeHtml(
                              aircraft.serial_number
                            )}<br>
                            <strong>FAA District:</strong> ${escapeHtml(
                              aircraft.faa_district
                            )}
                        </div>
                    `
                      )
                      .join('')}
                </div>
            `
                : ''
            }

            ${
              result.operators && result.operators.length > 0
                ? `
                <div class="result-section">
                    <h4>Operator Information</h4>
                    ${result.operators
                      .map((operator) => {
                        const score = operator.score || 0;
                        const scoreClass =
                          score >= 150
                            ? 'score-high'
                            : score >= 100
                            ? 'score-medium'
                            : 'score-low';
                        const hasCharterData = operator.charter_data !== null;

                        return `
                            <div class="base-card" style="background: white; padding: 20px; margin-bottom: 16px; border: 1px solid #e5e7eb;">
                                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                                    <div>
                                        <strong style="font-size: 16px;">${escapeHtml(
                                          operator.operator_name
                                        )}</strong>
                                        ${
                                          hasCharterData
                                            ? `<span class="score-badge ${scoreClass}" style="margin-left: 12px;">Score: ${score}</span>`
                                            : ''
                                        }
                                    </div>
                                </div>

                                <div style="margin-bottom: 8px;">
                                    <strong>Certificate Designator:</strong> ${escapeHtml(
                                      operator.certificate_designator
                                    )}
                                </div>

                                ${
                                  hasCharterData &&
                                  operator.charter_data.certifications
                                    ? `
                                    <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #e5e7eb;">
                                        <strong style="display: block; margin-bottom: 12px;">Certifications:</strong>
                                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                                            ${
                                              operator.charter_data
                                                .certifications
                                                .wyvern_certified &&
                                              operator.charter_data
                                                .certifications
                                                .wyvern_certified !== 'No'
                                                ? `
                                                <div class="cert-item">
                                                    <strong>Wyvern:</strong> ${escapeHtml(
                                                      operator.charter_data
                                                        .certifications
                                                        .wyvern_certified
                                                    )}
                                                </div>
                                            `
                                                : ''
                                            }
                                            ${
                                              operator.charter_data
                                                .certifications.argus_rating &&
                                              operator.charter_data
                                                .certifications.argus_rating !==
                                                'No'
                                                ? `
                                                <div class="cert-item">
                                                    <strong>ARGUS:</strong> ${escapeHtml(
                                                      operator.charter_data
                                                        .certifications
                                                        .argus_rating
                                                    )}
                                                </div>
                                            `
                                                : ''
                                            }
                                            ${
                                              operator.charter_data
                                                .certifications.is_bao &&
                                              operator.charter_data
                                                .certifications.is_bao !== 'No'
                                                ? `
                                                <div class="cert-item">
                                                    <strong>IS-BAO:</strong> ${escapeHtml(
                                                      operator.charter_data
                                                        .certifications.is_bao
                                                    )}
                                                </div>
                                            `
                                                : ''
                                            }
                                            ${
                                              operator.charter_data
                                                .certifications.acsf_ias &&
                                              operator.charter_data
                                                .certifications.acsf_ias !==
                                                'No'
                                                ? `
                                                <div class="cert-item">
                                                    <strong>ACSF IAS:</strong> ${escapeHtml(
                                                      operator.charter_data
                                                        .certifications.acsf_ias
                                                    )}
                                                </div>
                                            `
                                                : ''
                                            }
                                        </div>
                                    </div>
                                `
                                    : `
                                    <div style="margin-top: 12px; padding: 12px; background: #fef3c7; border-radius: 6px; color: #92400e;">
                                        <strong>Note:</strong> No charter operator data available for this Part 135 operator
                                    </div>
                                `
                                }

                                ${
                                  hasCharterData &&
                                  operator.charter_data.contact
                                    ? `
                                    <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #e5e7eb;">
                                        <strong style="display: block; margin-bottom: 12px;">Contact Information:</strong>
                                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
                                            ${
                                              operator.charter_data.contact
                                                .telephone
                                                ? `
                                                <div><strong>Phone:</strong> ${escapeHtml(
                                                  operator.charter_data.contact
                                                    .telephone
                                                )}</div>
                                            `
                                                : ''
                                            }
                                            ${
                                              operator.charter_data.contact
                                                .email
                                                ? `
                                                <div><strong>Email:</strong> <a href="mailto:${escapeHtml(
                                                  operator.charter_data.contact
                                                    .email
                                                )}">${escapeHtml(
                                                    operator.charter_data
                                                      .contact.email
                                                  )}</a></div>
                                            `
                                                : ''
                                            }
                                            ${
                                              operator.charter_data.contact
                                                .website
                                                ? `
                                                <div><strong>Website:</strong> <a href="${escapeHtml(
                                                  operator.charter_data.contact
                                                    .website
                                                )}" target="_blank">${escapeHtml(
                                                    operator.charter_data
                                                      .contact.website
                                                  )}</a></div>
                                            `
                                                : ''
                                            }
                                        </div>
                                    </div>
                                `
                                    : ''
                                }
                            </div>
                        `;
                      })
                      .join('')}
                </div>
            `
                : ''
            }
        </div>
    `;

  tailResults.innerHTML = html;
}

// Clear tail search
function clearTailSearch() {
  tailSearchInput.value = '';
  tailResults.innerHTML = '';
  tailError.style.display = 'none';
}

// Tail search event listeners
tailSearchBtn.addEventListener('click', searchTailNumber);
tailClearBtn.addEventListener('click', clearTailSearch);
tailSearchInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') {
    searchTailNumber();
  }
});

// Run Score functionality for Charter Operators
async function runCharterScore(operatorName, certificateDesignator, faaState) {
  try {
    // Pass faaState to backend (backend handles validation)
    const validFaaState = faaState || '';

    const BACKEND_API_URL = 'http://localhost:8000';

    // Step 1: Create Browserbase session and get live view URL immediately
    modal.style.display = 'block';
    modalBody.innerHTML =
      '<div class="loading-modal">Creating Browserbase session...<br><small style="opacity: 0.8; margin-top: 8px; display: block;">Loading live viewer...</small></div>';

    const sessionResponse = await fetch(
      `${BACKEND_API_URL}/scoring/start-session?operator_name=${encodeURIComponent(
        operatorName
      )}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    if (!sessionResponse.ok) {
      const errorData = await sessionResponse
        .json()
        .catch(() => ({ detail: 'Failed to create Browserbase session' }));
      throw new Error(errorData.detail || 'Failed to create Browserbase session');
    }

    const sessionData = await sessionResponse.json();

    // Step 2: Create split-screen layout with live view on left
    console.log('Embedding Browserbase live view in modal...');
    modalBody.innerHTML = `
      <div style="display: flex; gap: 16px; height: 80vh; min-height: 600px;">
        <!-- Left side: Live Browser View -->
        <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
          <div style="padding: 12px; background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; border-radius: 8px 8px 0 0; font-weight: 600; text-align: center;">
            🎥 Live Browser Session
          </div>
          <iframe
            src="${sessionData.live_view_url}"
            sandbox="allow-same-origin allow-scripts"
            allow="clipboard-read; clipboard-write"
            style="flex: 1; border: 2px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; background: white;"
          ></iframe>
        </div>

        <!-- Right side: Results -->
        <div style="flex: 1; display: flex; flex-direction: column; overflow-y: auto; min-width: 0;" id="resultsPanel">
          <div class="loading-modal" style="padding: 40px; text-align: center;">
            Running automation...<br>
            <small style="opacity: 0.8; margin-top: 12px; display: block;">👀 Watch the live browser on the left!</small>
            <br>
            <small style="opacity: 0.8; margin-top: 8px; display: block;">Step 1: Querying NTSB database...</small>
            <br>
            <small style="opacity: 0.8; margin-top: 4px; display: block;">Step 2: Verifying UCC filings...</small>
            <br>
            <small style="opacity: 0.6; margin-top: 8px; display: block;">This may take 10-30 seconds...</small>
          </div>
        </div>
      </div>
    `;

    // Step 3: Run full scoring flow using the existing session
    const scoreResponse = await fetch(
      `${BACKEND_API_URL}/scoring/full-scoring-flow?operator_name=${encodeURIComponent(
        operatorName
      )}&faa_state=${encodeURIComponent(validFaaState)}&session_id=${sessionData.session_id}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );

    if (!scoreResponse.ok) {
      const errorData = await scoreResponse
        .json()
        .catch(() => ({ detail: 'Score calculation failed' }));
      throw new Error(errorData.detail || 'Score calculation failed');
    }

    const scoreResult = await scoreResponse.json();

    // Step 4: Display the results on the right side panel
    displayFullScoringResults(operatorName, scoreResult, true);
  } catch (error) {
    console.error('Scoring flow error:', error);
    modalBody.innerHTML = `
            <div class="detail-section">
                <h2>Scoring Flow Error</h2>
                <p style="color: #e74c3c;">${escapeHtml(error.message)}</p>
                <p style="margin-top: 16px;">
                    <strong>Possible reasons:</strong><br>
                    • NTSB API is slow or unavailable<br>
                    • Browserbase credentials not configured<br>
                    • Backend server is not running<br>
                    • Network connectivity issues
                </p>
                <p style="margin-top: 12px;">Please try again in a moment.</p>
            </div>
        `;
  }
}

// Display full scoring flow results (NTSB + UCC)
function displayFullScoringResults(operatorName, data, isSplitView = false) {
  const ntsbData = data.ntsb || {};
  const uccData = data.ucc || {};
  const ntsb_score = ntsbData.score || 0;
  const total_incidents = ntsbData.total_incidents || 0;
  const incidents = ntsbData.incidents || [];

  const scoreColor =
    ntsb_score >= 80 ? '#10b981' : ntsb_score >= 60 ? '#f59e0b' : '#ef4444';

  let content = `
        <div class="detail-section">
            <h2>${escapeHtml(operatorName)} - Full Scoring Report</h2>

            ${!isSplitView && uccData.browserbase_live_view_url ? `
                <div style="margin: 20px 0; padding: 24px; background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); border-radius: 12px; text-align: center; box-shadow: 0 8px 16px rgba(37, 99, 235, 0.3);">
                    <div style="color: white; font-size: 20px; font-weight: 700; margin-bottom: 8px;">
                        🎥 Live Browser Automation Session
                    </div>
                    <div style="color: rgba(255,255,255,0.9); font-size: 14px; margin-bottom: 20px; line-height: 1.5;">
                        A new window has opened showing the live browser automation.<br>
                        Watch as the system navigates the UCC filings page in real-time!
                    </div>
                    <a href="${escapeHtml(uccData.browserbase_live_view_url)}" target="_blank"
                       style="display: inline-block; padding: 12px 32px; background: white; color: #2563eb; text-decoration: none; border-radius: 8px; font-weight: 700; font-size: 15px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); transition: all 0.2s;"
                       onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 12px rgba(0,0,0,0.15)'"
                       onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.1)'">
                        🔗 Open Session Viewer
                    </a>
                    <div style="color: rgba(255,255,255,0.7); font-size: 12px; margin-top: 16px;">
                        Session ID: ${escapeHtml(uccData.browserbase_session_id || 'N/A')}
                    </div>
                </div>
            ` : ''}

            <div style="margin-top: 20px;">
                <div style="display: inline-block; padding: 20px 40px; background: linear-gradient(135deg, ${scoreColor} 0%, ${scoreColor}dd 100%); border-radius: 12px; color: white;">
                    <div style="font-size: 14px; opacity: 0.9; margin-bottom: 8px;">COMBINED SAFETY SCORE</div>
                    <div style="font-size: 48px; font-weight: bold;">${data.combined_score || ntsb_score}</div>
                    <div style="font-size: 14px; opacity: 0.9; margin-top: 4px;">out of 100</div>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h2>📊 NTSB Safety Report</h2>
            <div style="padding: 16px; background: #f9fafb; border-radius: 8px; margin-bottom: 16px;">
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
                    <div>
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">NTSB SCORE</div>
                        <div style="font-size: 24px; font-weight: bold; color: ${scoreColor};">${ntsb_score}/100</div>
                    </div>
                    <div>
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">TOTAL INCIDENTS</div>
                        <div style="font-size: 24px; font-weight: bold;">${total_incidents}</div>
                    </div>
                </div>
            </div>
    `;

  if (incidents && incidents.length > 0) {
    content += `
            <h3 style="margin-top: 20px; margin-bottom: 12px;">Incident Reports (${total_incidents})</h3>
            <div style="max-height: 300px; overflow-y: auto;">
                ${incidents.slice(0, 5)
                  .map((incident, index) => {
                    const injuryLevel = incident.injury_level || 'Unknown';
                    let severityColor = '#10b981';
                    if (injuryLevel.toLowerCase().includes('fatal'))
                      severityColor = '#ef4444';
                    else if (injuryLevel.toLowerCase().includes('serious'))
                      severityColor = '#f59e0b';

                    return `
                        <div style="padding: 12px; margin-bottom: 8px; background: white; border-left: 4px solid ${severityColor}; border-radius: 6px;">
                            <div style="font-weight: 600; margin-bottom: 4px;">${escapeHtml(
                              incident.event_id || 'Incident #' + (index + 1)
                            )}</div>
                            <div style="font-size: 13px; color: #6b7280;">
                                ${incident.event_date ? new Date(incident.event_date).toLocaleDateString() : 'N/A'}
                                ${incident.location ? ` • ${escapeHtml(incident.location)}` : ''}
                            </div>
                        </div>
                    `;
                  })
                  .join('')}
                ${total_incidents > 5 ? `<div style="text-align: center; padding: 8px; color: #6b7280; font-size: 12px;">Showing 5 of ${total_incidents} incidents</div>` : ''}
            </div>
        `;
  } else {
    content += `
            <div style="padding: 20px; text-align: center; background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; color: #166534;">
                <div style="font-size: 32px; margin-bottom: 8px;">✓</div>
                <strong>No NTSB Incidents Found</strong>
            </div>
        `;
  }
  content += `</div>`;

  // UCC Section
  content += `
        <div class="detail-section">
            <h2>📑 UCC Filing Verification Results</h2>
            <div style="padding: 16px; background: #f9fafb; border-radius: 8px;">
                <div style="margin-bottom: 12px;">
                    <strong>Status:</strong> <span style="color: #6b7280;">${escapeHtml(uccData.status || 'N/A')}</span>
                </div>
                ${uccData.message ? `<div style="margin-bottom: 12px;"><strong>Message:</strong> ${escapeHtml(uccData.message)}</div>` : ''}
                ${uccData.jurisdictions_found ? `<div style="margin-bottom: 12px;"><strong>Jurisdictions Found:</strong> ${uccData.jurisdictions_found}</div>` : ''}
                ${uccData.browserbase_session_id ? `
                    <div style="margin-top: 12px; padding: 12px; background: #e0e7ff; border-radius: 6px;">
                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 4px;">Session ID</div>
                        <code style="color: #4338ca; font-size: 11px; background: white; padding: 4px 8px; border-radius: 4px; display: inline-block;">${escapeHtml(uccData.browserbase_session_id)}</code>
                    </div>
                ` : ''}
            </div>
        </div>
    `;

  // Update the appropriate container based on view mode
  if (isSplitView) {
    const resultsPanel = document.getElementById('resultsPanel');
    if (resultsPanel) {
      resultsPanel.innerHTML = content;
    }
  } else {
    modalBody.innerHTML = content;
  }
}

// Display charter score calculation results
function displayCharterScoreResults(operatorName, scoreData) {
  const {
    operator_name,
    ntsb_score,
    total_incidents,
    incidents,
    calculated_at,
  } = scoreData;

  const scoreColor =
    ntsb_score >= 80 ? '#10b981' : ntsb_score >= 60 ? '#f59e0b' : '#ef4444';

  let content = `
        <div class="detail-section">
            <h2>${escapeHtml(operator_name || operatorName)}</h2>
            <div style="margin-top: 20px;">
                <div style="display: inline-block; padding: 20px 40px; background: linear-gradient(135deg, ${scoreColor} 0%, ${scoreColor}dd 100%); border-radius: 12px; color: white;">
                    <div style="font-size: 14px; opacity: 0.9; margin-bottom: 8px;">NTSB SAFETY SCORE</div>
                    <div style="font-size: 48px; font-weight: bold;">${ntsb_score}</div>
                    <div style="font-size: 14px; opacity: 0.9; margin-top: 4px;">out of 100</div>
                </div>
            </div>
            <div style="margin-top: 20px; padding: 12px; background: #f3f4f6; border-radius: 8px;">
                <strong>Total Incidents:</strong> ${total_incidents}<br>
                <strong>Calculated:</strong> ${new Date(
                  calculated_at
                ).toLocaleString()}
            </div>
        </div>
    `;

  if (incidents && incidents.length > 0) {
    content += `
            <div class="detail-section">
                <h3>NTSB Incident Reports (${total_incidents})</h3>
                <div style="max-height: 400px; overflow-y: auto;">
                    ${incidents
                      .map((incident, index) => {
                        // Format date
                        let formattedDate = 'N/A';
                        if (incident.event_date) {
                          try {
                            formattedDate = new Date(
                              incident.event_date
                            ).toLocaleDateString('en-US', {
                              year: 'numeric',
                              month: 'long',
                              day: 'numeric',
                            });
                          } catch (e) {
                            formattedDate = incident.event_date;
                          }
                        }

                        // Determine severity color
                        const injuryLevel = incident.injury_level || 'Unknown';
                        let severityColor = '#10b981'; // Green for none/minor
                        if (injuryLevel.toLowerCase().includes('fatal'))
                          severityColor = '#ef4444'; // Red
                        else if (injuryLevel.toLowerCase().includes('serious'))
                          severityColor = '#f59e0b'; // Orange

                        const eventType = incident.event_type || 'N/A';
                        const eventTypeColor =
                          eventType.toLowerCase() === 'accident'
                            ? '#ef4444'
                            : '#6b7280';

                        return `
                        <div style="padding: 16px; margin-bottom: 12px; background: white; border-left: 4px solid ${severityColor}; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                                <div>
                                    <strong style="font-size: 16px;">${
                                      incident.event_id
                                        ? escapeHtml(incident.event_id)
                                        : 'Incident #' + (index + 1)
                                    }</strong>
                                    <div style="margin-top: 4px; color: #6b7280; font-size: 14px;">
                                        <span style="display: inline-block; padding: 2px 8px; background: ${eventTypeColor}; color: white; border-radius: 4px; font-size: 12px; font-weight: 500;">
                                            ${escapeHtml(eventType)}
                                        </span>
                                    </div>
                                </div>
                                ${
                                  incident.injury_level
                                    ? `
                                    <div style="text-align: right;">
                                        <div style="font-size: 12px; color: #6b7280; margin-bottom: 2px;">Injury Level</div>
                                        <div style="font-weight: 600; color: ${severityColor};">${escapeHtml(
                                        injuryLevel
                                      )}</div>
                                    </div>
                                `
                                    : ''
                                }
                            </div>
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; font-size: 14px;">
                                <div>
                                    <div style="color: #6b7280; font-size: 12px; margin-bottom: 2px;">📅 Date</div>
                                    <div style="font-weight: 500;">${escapeHtml(
                                      formattedDate
                                    )}</div>
                                </div>
                                ${
                                  incident.location
                                    ? `
                                <div>
                                    <div style="color: #6b7280; font-size: 12px; margin-bottom: 2px;">📍 Location</div>
                                    <div style="font-weight: 500;">${escapeHtml(
                                      incident.location
                                    )}</div>
                                </div>
                                `
                                    : ''
                                }
                            </div>
                        </div>
                        `;
                      })
                      .join('')}
                </div>
            </div>
        `;
  } else {
    content += `
            <div class="detail-section">
                <div style="padding: 24px; text-align: center; background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; color: #166534;">
                    <div style="font-size: 48px; margin-bottom: 12px;">✓</div>
                    <strong style="font-size: 18px;">No NTSB Incidents Found</strong>
                    <p style="margin-top: 8px; font-size: 14px; opacity: 0.8;">This operator has a clean safety record with no incidents reported in the NTSB database.</p>
                </div>
            </div>
        `;
  }

  modalBody.innerHTML = content;
}

// Batch Verify All functionality - Calls backend batch-verify-by-states endpoint
async function runBatchVerify() {
  const BACKEND_API_URL = 'http://localhost:8000';
  const batchVerifyBtn = document.getElementById('batchVerifyBtn');

  try {
    // Disable button and show loading state
    batchVerifyBtn.disabled = true;
    batchVerifyBtn.textContent = '⏳ Creating session...';

    // Show modal with loading state
    modal.style.display = 'block';
    modalBody.innerHTML = `
      <div style="padding: 40px; text-align: center;">
        <div style="font-size: 48px; margin-bottom: 20px;">🔄</div>
        <h2 style="margin-bottom: 16px;">Creating Browserbase Session...</h2>
        <div class="loading-modal">Loading live viewer...</div>
      </div>
    `;

    // Step 1: Create Browserbase session first
    const sessionResponse = await fetch(
      `${BACKEND_API_URL}/scoring/start-session?operator_name=BatchVerification`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' } }
    );

    if (!sessionResponse.ok) {
      throw new Error('Failed to create Browserbase session');
    }

    const sessionData = await sessionResponse.json();

    // Step 2: Show split-screen with live view
    batchVerifyBtn.textContent = '⏳ Running batch verification...';
    modalBody.innerHTML = `
      <div style="display: flex; gap: 16px; height: 80vh; min-height: 600px;">
        <!-- Left side: Live Browser View -->
        <div style="flex: 1; display: flex; flex-direction: column; min-width: 0;">
          <div style="padding: 12px; background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%); color: white; border-radius: 8px 8px 0 0; font-weight: 600; text-align: center;">
            🎥 Live Browser Session
          </div>
          <iframe
            src="${sessionData.live_view_url}"
            sandbox="allow-same-origin allow-scripts"
            allow="clipboard-read; clipboard-write"
            style="flex: 1; border: 2px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; background: white;"
          ></iframe>
        </div>

        <!-- Right side: Progress -->
        <div style="flex: 1; display: flex; flex-direction: column; overflow-y: auto; min-width: 0;" id="resultsPanel">
          <div style="padding: 40px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 20px;">🔄</div>
            <h2 style="margin-bottom: 16px;">Batch Verification In Progress</h2>
            <div class="loading-modal">
              Running batch verification...<br>
              <small style="opacity: 0.8; margin-top: 12px; display: block;">👀 Watch the live browser on the left!</small>
              <br>
              <small style="opacity: 0.6; margin-top: 8px; display: block;">This may take several minutes...</small>
            </div>
          </div>
        </div>
      </div>
    `;

    // Step 3: Call backend batch-verify-by-states endpoint with session_id
    const response = await fetch(`${BACKEND_API_URL}/scoring/batch-verify-by-states?session_id=${sessionData.session_id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Batch verification failed' }));
      throw new Error(errorData.detail || 'Batch verification failed');
    }

    const batchResult = await response.json();

    // Show final results in the right panel (keep live view visible)
    const successfulOps = batchResult.results.filter(r => r.status === 'completed' || r.status === 'completed_with_errors');
    const failedOps = batchResult.results.filter(r => r.status === 'failed');

    const resultsPanel = document.getElementById('resultsPanel');
    if (resultsPanel) {
      resultsPanel.innerHTML = `
        <div style="padding: 20px;">
          <div style="text-align: center; margin-bottom: 24px;">
            <div style="font-size: 36px; margin-bottom: 12px;">✓</div>
            <h2 style="margin-bottom: 8px; font-size: 20px;">Batch Verification Complete!</h2>
            <p style="color: #6b7280;">Processed ${batchResult.total_operators} operators</p>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px;">
            <div style="padding: 16px; background: #f0fdf4; border: 2px solid #86efac; border-radius: 8px; text-align: center;">
              <div style="font-size: 24px; font-weight: bold; color: #16a34a;">${batchResult.successful}</div>
              <div style="color: #166534; margin-top: 4px; font-size: 14px;">Successful</div>
            </div>
            <div style="padding: 16px; background: #fef2f2; border: 2px solid #fca5a5; border-radius: 8px; text-align: center;">
              <div style="font-size: 24px; font-weight: bold; color: #dc2626;">${batchResult.failed}</div>
              <div style="color: #991b1b; margin-top: 4px; font-size: 14px;">Failed</div>
            </div>
          </div>

          ${successfulOps.length > 0 ? `
            <div style="margin-bottom: 16px;">
              <h3 style="margin-bottom: 8px; color: #16a34a; font-size: 14px;">✓ Successfully Verified</h3>
              <div style="max-height: 200px; overflow-y: auto; background: #f9fafb; border-radius: 8px; padding: 8px;">
                ${successfulOps.map(op => `
                  <div style="padding: 6px; margin-bottom: 6px; background: white; border-left: 3px solid #16a34a; border-radius: 4px; font-size: 13px;">
                    <strong>${escapeHtml(op.operator_name)}</strong>
                    <span style="color: #6b7280; font-size: 12px; margin-left: 6px;">(${op.faa_state})</span>
                    ${op.trust_score ? `<span style="float: right; color: #16a34a;">Score: ${Math.round(op.trust_score)}</span>` : ''}
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          ${failedOps.length > 0 ? `
            <div style="margin-bottom: 16px;">
              <h3 style="margin-bottom: 8px; color: #dc2626; font-size: 14px;">✗ Failed</h3>
              <div style="max-height: 150px; overflow-y: auto; background: #f9fafb; border-radius: 8px; padding: 8px;">
                ${failedOps.map(op => `
                  <div style="padding: 6px; margin-bottom: 6px; background: white; border-left: 3px solid #dc2626; border-radius: 4px; font-size: 13px;">
                    <strong>${escapeHtml(op.operator_name)}</strong>
                    ${op.error ? `<div style="font-size: 11px; color: #dc2626; margin-top: 2px;">${escapeHtml(op.error)}</div>` : ''}
                  </div>
                `).join('')}
              </div>
            </div>
          ` : ''}

          <div style="margin-top: 20px; text-align: center;">
            <button onclick="modal.style.display='none'" style="padding: 10px 24px; background: #2563eb; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px;">Close</button>
          </div>
        </div>
      `;
    }

  } catch (error) {
    console.error('Batch verification error:', error);
    modalBody.innerHTML = `
      <div style="padding: 40px; text-align: center;">
        <div style="font-size: 48px; margin-bottom: 20px; color: #dc2626;">✗</div>
        <h2 style="margin-bottom: 16px; color: #dc2626;">Batch Verification Failed</h2>
        <p style="color: #6b7280; margin-bottom: 24px;">${escapeHtml(error.message)}</p>
        <button onclick="modal.style.display='none'" style="padding: 12px 32px; background: #dc2626; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px;">Close</button>
      </div>
    `;
  } finally {
    // Re-enable button
    batchVerifyBtn.disabled = false;
    batchVerifyBtn.innerHTML = '▶ Batch Verify All';
  }
}

// Add event listener for batch verify button
document.addEventListener('DOMContentLoaded', function() {
  const batchVerifyBtn = document.getElementById('batchVerifyBtn');
  if (batchVerifyBtn) {
    batchVerifyBtn.addEventListener('click', runBatchVerify);
  }
});
