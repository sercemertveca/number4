from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'secret_key_for_sessions'

DB = 'books.db'

#  Инициализация базы 
def init_db():
    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                author TEXT,
                category TEXT,
                year INTEGER,
                price REAL,
                status TEXT DEFAULT 'available',
                rented_until DATE
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                is_admin INTEGER DEFAULT 0
            )
        ''')
        # Добавим пару книг для примера, если их нет
        cur.execute("SELECT COUNT(*) FROM books")
        if cur.fetchone()[0] == 0:
            cur.executemany('''
                INSERT INTO books (title, author, category, year, price) VALUES (?, ?, ?, ?, ?)
            ''', [
                ("Книга 1", "Автор 1", "Фантастика", 2000, 300),
                ("Книга 2", "Автор 2", "Техническая", 2001, 400),
                ("Книга 3", "Автор 3", "Классика", 2002, 350)
            ])
        # Добавим админа, если нет
        cur.execute("SELECT COUNT(*) FROM users WHERE is_admin=1")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)", ("admin", "admin", 1))
        con.commit()

init_db()

#  Хелпер к базе 
def query_db(query, args=(), one=False):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(query, args)
        rv = cur.fetchall()
        return (rv[0] if rv else None) if one else rv

#  Регистрация 
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role')  # admin или user
        is_admin = 1 if role == 'admin' else 0

        try:
            with sqlite3.connect(DB) as con:
                cur = con.cursor()
                cur.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                            (username, password, is_admin))
                con.commit()
            flash('Регистрация прошла успешно! Войдите в аккаунт.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Пользователь с таким именем уже существует.')
    return render_template('register.html')

#  Аутентификация 
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']
        user_data = query_db('SELECT * FROM users WHERE username=? AND password=?', (user, pwd), one=True)
        if user_data:
            session['user_id'] = user_data['id']
            session['username'] = user_data['username']
            session['is_admin'] = bool(user_data['is_admin'])
            return redirect(url_for('admin' if session['is_admin'] else 'index'))
        else:
            flash('Неверный логин или пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

#  Пользовательский интерфейс 
@app.route('/')
def index():
    category = request.args.get('category')
    author = request.args.get('author')
    year = request.args.get('year')

    query = "SELECT * FROM books WHERE status='available'"
    params = []
    filters = []
    if category:
        filters.append("category=?")
        params.append(category)
    if author:
        filters.append("author=?")
        params.append(author)
    if year:
        filters.append("year=?")
        params.append(year)
    if filters:
        query += " AND " + " AND ".join(filters)
    books = query_db(query, params)

    categories = [r['category'] for r in query_db("SELECT DISTINCT category FROM books")]
    authors = [r['author'] for r in query_db("SELECT DISTINCT author FROM books")]
    years = [r['year'] for r in query_db("SELECT DISTINCT year FROM books")]

    return render_template('index.html', books=books, categories=categories, authors=authors, years=years)

@app.route('/book/<int:book_id>')
def book_detail(book_id):
    book = query_db('SELECT * FROM books WHERE id=?', (book_id,), one=True)
    if not book:
        return "Книга не найдена", 404
    return render_template('book_detail.html', book=book)

@app.route('/rent/<int:book_id>', methods=['POST'])
def rent(book_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    period = request.form.get('period')  # 2weeks / 1month / 3months
    days_map = {'2weeks': 14, '1month': 30, '3months': 90}
    if period not in days_map:
        flash('Неправильный срок аренды')
        return redirect(url_for('book_detail', book_id=book_id))

    rent_days = days_map[period]
    rented_until = datetime.now() + timedelta(days=rent_days)

    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute("SELECT status FROM books WHERE id=?", (book_id,))
        status = cur.fetchone()
        if not status or status[0] != 'available':
            flash('Книга недоступна')
            return redirect(url_for('index'))
        cur.execute("UPDATE books SET status='rented', rented_until=? WHERE id=?", (rented_until.date(), book_id))
        con.commit()
    flash(f'Вы арендовали книгу на {period.replace("1month", "1 месяц").replace("2weeks", "2 недели").replace("3months", "3 месяца")}')
    return redirect(url_for('index'))

@app.route('/buy/<int:book_id>', methods=['POST'])
def buy(book_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    with sqlite3.connect(DB) as con:
        cur = con.cursor()
        cur.execute("SELECT status FROM books WHERE id=?", (book_id,))
        status = cur.fetchone()
        if not status or status[0] != 'available':
            flash('Книга недоступна')
            return redirect(url_for('index'))
        cur.execute("UPDATE books SET status='sold' WHERE id=?", (book_id,))
        con.commit()
    flash('Вы купили книгу!')
    return redirect(url_for('index'))

#  Админка 
@app.route('/admin')
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    books = query_db("SELECT * FROM books")
    notifications = []
    today = datetime.now().date()
    for book in books:
        if book['status'] == 'rented' and book['rented_until']:
            due_date = datetime.strptime(book['rented_until'], '%Y-%m-%d').date()
            days_left = (due_date - today).days
            if days_left <= 3:
                notifications.append(f"Книга '{book['title']}' аренда заканчивается через {days_left} дн.")
    return render_template('admin.html', books=books, notifications=notifications)

@app.route('/admin/edit/<int:book_id>', methods=['GET', 'POST'])
def admin_edit(book_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    book = query_db("SELECT * FROM books WHERE id=?", (book_id,), one=True)
    if not book:
        return "Книга не найдена", 404
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        category = request.form['category']
        year = int(request.form['year'])
        price = float(request.form['price'])
        status = request.form['status']
        with sqlite3.connect(DB) as con:
            cur = con.cursor()
            cur.execute('''
                UPDATE books SET title=?, author=?, category=?, year=?, price=?, status=? WHERE id=?
            ''', (title, author, category, year, price, status, book_id))
            con.commit()
        flash('Книга обновлена')
        return redirect(url_for('admin'))
    return render_template('admin_edit.html', book=book)

@app.route('/admin/add', methods=['GET', 'POST'])
def admin_add():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        category = request.form['category']
        year = int(request.form['year'])
        price = float(request.form['price'])
        with sqlite3.connect(DB) as con:
            cur = con.cursor()
            cur.execute('''
                INSERT INTO books (title, author, category, year, price, status) VALUES (?, ?, ?, ?, ?, 'available')
            ''', (title, author, category, year, price))
            con.commit()
        flash('Книга успешно добавлена!')
        return redirect(url_for('admin'))
    return render_template('admin_add.html')

if __name__ == '__main__':
    app.run(debug=True)
