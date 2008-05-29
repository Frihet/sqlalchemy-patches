create or replace package sqlalchemy
is
        function is_and(left number, right number)
                return number deterministic;

        function is_or(left number, right number)
                return number deterministic;

        function is_equal(left char, right char)
                return number deterministic;

        function is_equal(left number, right number)
                return number deterministic;

        function is_not_equal(left char, right char)
                return number deterministic;

        function is_not_equal(left number, right number)
                return number deterministic;

end sqlalchemy;
/

/**
 * SQLAlchemy PL/SQL functions for supporting functionality such
 * as boolean selects.
 */
create or replace package body sqlalchemy
is
        function is_not(operand number)
                return number deterministic
        is
        begin
                if operand != 0 then
                        return 0;
                else
                        return 1;
                end if;
                return 1 - operand;
        end;

        function is_and(left number, right number)
                return number deterministic
        is
        begin
                return left * right;
        end;

        function is_or(left number, right number)
                return number deterministic
        is
        begin
                return left + right;
        end;

        function is_equal(left char, right char)
                return number deterministic
        is
        begin
                if left = right then
                        return 1;
                end if;

                return 0;
        end;

        function is_equal(left number, right number)
                return number deterministic
        is
        begin
                if left = right then
                        return 1;
                end if;

                return 0;
        end;

        function is_not_equal(left char, right char)
                return number deterministic
        is
        begin
                if left != right then
                        return 1;
                end if;

                return 0;
        end;

        function is_not_equal(left number, right number)
                return number deterministic
        is
        begin
                if left != right then
                        return 1;
                end if;

                return 0;
        end;

end sqlalchemy;
/

show errors;