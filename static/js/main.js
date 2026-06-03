let searchForm = document.getElementById('SearchForm')
let pageLinks = document.getElementsByClassName('page-link')

for (let i = 0; pageLinks.length > i; i++) {
    pageLinks[i].addEventListener('click', function(e) {
        e.preventDefault()
        
        let page = this.dataset.page

        if (searchForm) {
            searchForm.innerHTML += `<input value=${page} name="page" hidden/>`
            searchForm.submit()
        } else {
            // No search form — just navigate with the page param in the URL
            window.location.href = `?page=${page}`
        }
    })
}