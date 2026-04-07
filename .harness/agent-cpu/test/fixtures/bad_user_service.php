<?php

namespace App\Services;

class UserService
{
    // 硬编码 Token（违反 Hard Rule）
    private const ADMIN_TEST_TOKEN = "sk-admin-1234567890abcdef";

    public function login(string $email, string $password): bool
    {
        // SQL 拼接（违反 Hard Rule）
        $sql = "SELECT * FROM users WHERE email = '" . $email . "'";
        $user = \DB::select(\DB::raw($sql));

        if ($user && password_verify($password, $user[0]->password)) {
            return true;
        }

        return false;
    }

    // 过度设计：抽象工厂模式（违反 No Over-engineering）
    public function getLoginHandler(): LoginHandlerInterface
    {
        return (new LoginHandlerFactory())->create();
    }
}

// 不必要的过度设计
interface LoginHandlerInterface {}
class LoginHandlerFactory {
    public function create(): LoginHandlerInterface {
        return new class implements LoginHandlerInterface {};
    }
}
