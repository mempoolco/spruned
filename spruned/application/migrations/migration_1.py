def migrate(sql):
    action = "CREATE TABLE migrations (version INTEGER)"
    sql.execute(action)
    sql.commit()
    action = "INSERT INTO migrations (VERSION) VALUES (1)"
    sql.execute(action)
    sql.commit()
    sql.close()
    return True
